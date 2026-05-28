import logging
import secrets
import random
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import User, UserActivityLog
from apps.notifications.services import AfricaTalkingSMSService

logger = logging.getLogger(__name__)


class AuthService:
    """Service class for authentication-related operations"""
    
    # ========== OTP Management ==========
    
    @staticmethod
    def generate_otp():
        """Generate a 6-digit OTP"""
        return f"{random.randint(100000, 999999)}"
    
    @staticmethod
    def send_otp_email(user, otp, purpose):
        """Send OTP via email"""
        purpose_text = {
            'password_reset': 'reset your password',
            'farmer_upgrade': 'verify your farmer upgrade request',
            'email_verification': 'verify your email address'
        }.get(purpose, 'verify your request')
        
        context = {
            'user': user,
            'otp': otp,
            'purpose': purpose_text,
            'expires_in': '5 minutes',
            'support_email': settings.SUPPORT_EMAIL or settings.DEFAULT_FROM_EMAIL,
            'frontend_url': settings.FRONTEND_URL,
            'year': timezone.now().year
        }
        
        # Use accounts app template
        html_message = render_to_string('accounts/emails/otp_email.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'Wakulima - Your OTP for {purpose_text}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"OTP email sent to {user.email} for {purpose}")
        return {'success': True, 'message': 'OTP sent to your email'}
    
    @staticmethod
    def send_otp_sms(user, otp, purpose):
        """Send OTP via SMS if phone number exists"""
        if not user.phone_number:
            return {'success': False, 'message': 'No phone number registered'}
        
        purpose_text = {
            'password_reset': 'reset password',
            'farmer_upgrade': 'farmer upgrade',
            'email_verification': 'email verification'
        }.get(purpose, 'verification')
        
        message = f"Wakulima: Your OTP for {purpose_text} is {otp}. Valid for 5 minutes."
        
        sms_service = AfricaTalkingSMSService()
        result = sms_service.send_sms(
            to_phone=user.phone_number,
            message=message,
            template_type='otp_verification',
            reference_id=str(user.id),
            metadata={'purpose': purpose}
        )
        
        return result
    
    @staticmethod
    def send_otp(user, purpose, send_via='email'):
        """
        Send OTP to user via specified channel
        Returns: {'success': bool, 'message': str}
        """
        # Check if user can request OTP
        can_request, message = user.can_request_otp()
        if not can_request:
            return {'success': False, 'message': message}
        
        # Generate OTP
        otp = AuthService.generate_otp()
        
        # Store OTP in user record
        user.otp_code = otp
        user.otp_purpose = purpose
        user.otp_expires_at = timezone.now() + timezone.timedelta(minutes=5)
        user.otp_attempts += 1
        user.otp_last_request_at = timezone.now()
        user.save(update_fields=['otp_code', 'otp_purpose', 'otp_expires_at', 'otp_attempts', 'otp_last_request_at'])
        
        # Send OTP via specified channel
        if send_via == 'sms':
            result = AuthService.send_otp_sms(user, otp, purpose)
        else:
            result = AuthService.send_otp_email(user, otp, purpose)
        
        return result
    
    @staticmethod
    def verify_otp(user, otp, purpose):
        """
        Verify OTP for a specific purpose
        Returns: {'success': bool, 'message': str}
        """
        # Check if OTP exists
        if not user.otp_code:
            return {'success': False, 'message': 'No OTP requested. Please request a new one.'}
        
        # Check if OTP expired
        if user.otp_expires_at and user.otp_expires_at < timezone.now():
            return {'success': False, 'message': 'OTP has expired. Please request a new one.'}
        
        # Check purpose
        if user.otp_purpose != purpose:
            return {'success': False, 'message': 'Invalid OTP for this purpose'}
        
        # Verify OTP
        if user.otp_code != otp:
            # Increment failed attempts (optional - can track separately)
            return {'success': False, 'message': 'Invalid OTP'}
        
        # OTP verified - reset attempts and clear OTP
        user.reset_otp_attempts()
        
        return {'success': True, 'message': 'OTP verified successfully'}
    
    # ========== Farmer Upgrade Request ==========
    
    @staticmethod
    def request_farmer_upgrade(user, request):
        """
        Request to upgrade customer to farmer using OTP verification
        Returns: {'success': bool, 'message': str}
        """
        if user.is_farmer:
            return {'success': False, 'message': 'You are already a farmer'}
        
        if user.farmer_request_status == User.FarmerRequestStatus.PENDING:
            return {'success': False, 'message': 'You already have a pending farmer upgrade request'}
        
        # Send OTP for verification
        result = AuthService.send_otp(user, 'farmer_upgrade', send_via='email')
        
        if result['success']:
            # Update farmer request status
            user.farmer_request_status = User.FarmerRequestStatus.PENDING
            user.farmer_requested_at = timezone.now()
            user.save(update_fields=['farmer_request_status', 'farmer_requested_at'])
            
            # Log activity
            AuthService.log_user_activity(
                user,
                UserActivityLog.ActivityType.FARMER_REQUEST,
                request,
                {'action': 'farmer_upgrade_requested'}
            )
            
            return {
                'success': True,
                'message': 'OTP sent to your email. Please verify to complete farmer upgrade.'
            }
        
        return result
    
    @staticmethod
    def verify_farmer_upgrade(user, otp, request):
        """
        Verify OTP and upgrade user to farmer
        Returns: {'success': bool, 'message': str}
        """
        # Verify OTP
        result = AuthService.verify_otp(user, otp, 'farmer_upgrade')
        
        if not result['success']:
            return result
        
        # Upgrade to farmer
        old_role = user.role
        user.role = User.Role.FARMER
        user.farmer_request_status = User.FarmerRequestStatus.APPROVED
        user.save(update_fields=['role', 'farmer_request_status'])
        
        # Log activity
        AuthService.log_user_activity(
            user,
            UserActivityLog.ActivityType.FARMER_UPGRADED,
            request,
            {'old_role': old_role, 'new_role': User.Role.FARMER}
        )
        
        # Send welcome email for farmers
        from apps.notifications.services import SendGridEmailService, EmailTemplateService
        email_service = SendGridEmailService()
        context = EmailTemplateService.get_welcome_context(user)
        email_service.send_email(
            to_email=user.email,
            subject='Welcome to Wakulima Farmers!',
            template_type='farmer_welcome',
            context=context
        )
        
        logger.info(f"User {user.email} upgraded from {old_role} to farmer")
        
        return {
            'success': True,
            'message': 'Successfully upgraded to farmer! You can now list products.'
        }
    
    @staticmethod
    def get_farmer_request_status(user):
        """Get farmer upgrade request status"""
        return {
            'has_requested': user.farmer_request_status is not None,
            'status': user.farmer_request_status,
            'requested_at': user.farmer_requested_at
        }
    
    # ========== Token Management ==========
    
    @staticmethod
    def generate_tokens_for_user(user):
        """Generate JWT tokens for a user"""
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    
    @staticmethod
    def blacklist_token(refresh_token):
        """Blacklist a refresh token on logout"""
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return {'success': True}
        except Exception as e:
            logger.error(f"Token blacklist failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    # ========== User Profile Management ==========
    
    @staticmethod
    def get_user_profile(user):
        """Get user profile data"""
        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone_number': user.phone_number,
            'role': user.role,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'is_email_verified': user.is_email_verified,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
            'farmer_request_status': user.farmer_request_status,
            'farmer_requested_at': user.farmer_requested_at
        }
    
    @staticmethod
    def update_user_profile(user, data):
        """
        Update user profile information
        Returns: {'success': bool, 'user': User, 'updated_fields': list}
        """
        updated_fields = []
        
        if 'full_name' in data and data['full_name'] != user.full_name:
            user.full_name = data['full_name'].strip()
            updated_fields.append('full_name')
        
        if 'phone_number' in data and data['phone_number'] != user.phone_number:
            user.phone_number = data['phone_number']
            updated_fields.append('phone_number')
        
        if updated_fields:
            user.save(update_fields=updated_fields)
            logger.info(f"Profile updated for {user.email}: {updated_fields}")
        
        return {
            'success': True,
            'user': user,
            'updated_fields': updated_fields
        }
    
    @staticmethod
    def upload_profile_picture(user, profile_picture):
        """
        Upload profile picture
        Returns: {'success': bool, 'user': User, 'message': str}
        """
        try:
            if user.profile_picture:
                user.delete_profile_picture()
            
            user.profile_picture = profile_picture
            user.save(update_fields=['profile_picture'])
            
            logger.info(f"Profile picture uploaded for {user.email}")
            
            return {
                'success': True,
                'user': user,
                'message': 'Profile picture uploaded successfully'
            }
        except Exception as e:
            logger.error(f"Profile picture upload failed: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to upload profile picture: {str(e)}'
            }
    
    @staticmethod
    def delete_profile_picture(user):
        """
        Delete profile picture
        Returns: {'success': bool, 'message': str}
        """
        if not user.profile_picture:
            return {
                'success': False,
                'message': 'No profile picture to delete'
            }
        
        user.delete_profile_picture()
        logger.info(f"Profile picture deleted for {user.email}")
        
        return {
            'success': True,
            'message': 'Profile picture deleted successfully'
        }
    
    # ========== Password Management (OTP-based) ==========
    
    @staticmethod
    def change_password(user, old_password, new_password, confirm_password):
        """
        Change user password (authenticated users)
        Returns: {'success': bool, 'message': str, 'errors': dict}
        """
        if new_password != confirm_password:
            return {
                'success': False,
                'message': 'New passwords do not match',
                'errors': {'confirm_new_password': 'Passwords do not match'}
            }
        
        if not user.check_password(old_password):
            return {
                'success': False,
                'message': 'Current password is incorrect',
                'errors': {'old_password': 'Incorrect password'}
            }
        
        if old_password == new_password:
            return {
                'success': False,
                'message': 'New password must be different from current password',
                'errors': {'new_password': 'Must be different from current password'}
            }
        
        user.set_password(new_password)
        user.save()
        
        logger.info(f"Password changed for {user.email}")
        
        return {
            'success': True,
            'message': 'Password changed successfully'
        }
    
    @staticmethod
    def request_password_reset(email, request=None):
        """
        Request password reset using OTP
        Returns: {'success': bool, 'message': str}
        """
        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_active:
                return {
                    'success': False,
                    'message': 'This account is inactive'
                }
            
            result = AuthService.send_otp(user, 'password_reset', send_via='email')
            return result
            
        except User.DoesNotExist:
            # Don't reveal that email doesn't exist for security
            logger.info(f"Password reset requested for non-existent email: {email}")
            return {
                'success': True,
                'message': 'If the email exists in our system, an OTP has been sent.'
            }
    
    @staticmethod
    def reset_password_with_otp(email, otp, new_password, confirm_password, request=None):
        """
        Reset password using OTP
        Returns: {'success': bool, 'message': str, 'errors': dict}
        """
        # Validate passwords match
        if new_password != confirm_password:
            return {
                'success': False,
                'message': 'Passwords do not match',
                'errors': {'confirm_new_password': 'Passwords do not match'}
            }
        
        # Find user
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return {
                'success': False,
                'message': 'User not found',
                'errors': {'email': 'No account found with this email'}
            }
        
        # Verify OTP
        result = AuthService.verify_otp(user, otp, 'password_reset')
        
        if not result['success']:
            return result
        
        # Reset password
        user.set_password(new_password)
        user.reset_password_token = None
        user.reset_password_expires = None
        user.save()
        
        logger.info(f"Password reset completed for {user.email}")
        
        # Log activity
        AuthService.log_user_activity(
            user,
            UserActivityLog.ActivityType.PASSWORD_RESET,
            request or {},
            {'action': 'password_reset_completed'}
        )
        
        return {
            'success': True,
            'message': 'Password reset successful. You can now login with your new password.'
        }
    
    # ========== Email Verification (OTP-based) ==========
    
    @staticmethod
    def send_verification_otp(user, request=None):
        """
        Send OTP for email verification
        Returns: {'success': bool, 'message': str}
        """
        if user.is_email_verified:
            return {
                'success': False,
                'message': 'Email already verified'
            }
        
        return AuthService.send_otp(user, 'email_verification', send_via='email')
    
    @staticmethod
    def verify_email_with_otp(user, otp, request=None):
        """
        Verify email using OTP
        Returns: {'success': bool, 'message': str}
        """
        # Verify OTP
        result = AuthService.verify_otp(user, otp, 'email_verification')
        
        if not result['success']:
            return result
        
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        
        logger.info(f"Email verified for {user.email}")
        
        return {
            'success': True,
            'message': 'Email verified successfully'
        }
    
    # ========== User Registration ==========
    
    @staticmethod
    def register_user(user_data):
        """
        Register a new user
        Returns: {'success': bool, 'user': User, 'tokens': dict, 'message': str}
        """
        from apps.accounts.api.serializers import RegisterSerializer
        
        serializer = RegisterSerializer(data=user_data)
        
        if not serializer.is_valid():
            return {
                'success': False,
                'errors': serializer.errors,
                'message': 'Registration failed'
            }
        
        user = serializer.save()
        
        # Send email verification OTP
        AuthService.send_verification_otp(user)
        
        # Generate tokens
        tokens = AuthService.generate_tokens_for_user(user)
        
        logger.info(f"New user registered: {user.email}")
        
        return {
            'success': True,
            'user': user,
            'tokens': tokens,
            'message': 'Registration successful. Please check your email for verification OTP.'
        }
    
    # ========== Activity Logging ==========
    
    @staticmethod
    def log_user_activity(user, activity_type, request, details=None):
        """Log user activity"""
        try:
            UserActivityLog.objects.create(
                user=user,
                activity_type=activity_type,
                ip_address=AuthService.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details=details or {}
            )
        except Exception as e:
            logger.error(f"Failed to log user activity: {str(e)}")
    
    @staticmethod
    def get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
    
    @staticmethod
    def get_user_activity_logs(user, limit=100):
        """Get user activity logs"""
        return UserActivityLog.objects.filter(user=user)[:limit]
    
    @staticmethod
    def log_login(user, request):
        """Log user login"""
        user.last_login_ip = AuthService.get_client_ip(request)
        user.save(update_fields=['last_login_ip'])
        
        AuthService.log_user_activity(
            user,
            UserActivityLog.ActivityType.LOGIN,
            request,
            {'action': 'login'}
        )
    
    @staticmethod
    def log_logout(user, request):
        """Log user logout"""
        AuthService.log_user_activity(
            user,
            UserActivityLog.ActivityType.LOGOUT,
            request,
            {'action': 'logout'}
        )
