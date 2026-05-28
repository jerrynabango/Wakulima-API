from rest_framework import status, generics, permissions, throttling
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging

from apps.accounts.models import User, UserActivityLog
from apps.accounts.api.serializers import (
    UserSerializer, UserProfileUpdateSerializer, ProfilePictureSerializer,
    RegisterSerializer, ChangePasswordSerializer, ForgotPasswordSerializer,
    UserActivityLogSerializer,
    # OTP and Farmer serializers
    RequestOTPSerializer, VerifyOTPSerializer, ResetPasswordWithOTPSerializer,
    FarmerUpgradeRequestSerializer, FarmerUpgradeVerifySerializer,
    FarmerRequestStatusSerializer
)
from apps.accounts.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class RegisterThrottle(throttling.SimpleRateThrottle):
    """Throttle for registration endpoint"""
    scope = 'register'
    
    def get_cache_key(self, request, view):
        if request.method == 'POST' and request.data.get('email'):
            return self.cache_format % {
                'scope': self.scope,
                'ident': request.data.get('email')
            }
        return None


class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]
    
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=RegisterSerializer,
        responses={
            201: openapi.Response('User created successfully', UserSerializer),
            400: 'Bad request'
        }
    )
    def post(self, request, *args, **kwargs):
        result = AuthService.register_user(request.data)
        
        if result['success']:
            # Log activity
            AuthService.log_user_activity(
                result['user'],
                UserActivityLog.ActivityType.LOGIN,
                request,
                {'action': 'registration'}
            )
            
            return Response({
                'user': UserSerializer(result['user']).data,
                'tokens': result['tokens'],
                'message': result['message']
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'errors': result.get('errors', {}), 'message': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom token obtain view with activity logging"""
    
    @swagger_auto_schema(
        operation_description="Login with email and password to get JWT tokens",
        responses={
            200: 'Login successful',
            401: 'Invalid credentials'
        }
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            email = request.data.get('email')
            try:
                user = User.objects.get(email__iexact=email)
                AuthService.log_login(user, request)
            except User.DoesNotExist:
                pass
        
        return response


class LogoutView(APIView):
    """Logout user by blacklisting refresh token"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Logout user and invalidate refresh token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token')
            }
        ),
        responses={
            205: 'Logout successful',
            400: 'Bad request'
        }
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = AuthService.blacklist_token(refresh_token)
        
        if result['success']:
            AuthService.log_logout(request.user, request)
            return Response(
                {'message': 'Successfully logged out'},
                status=status.HTTP_205_RESET_CONTENT
            )
        else:
            return Response(
                {'error': result.get('error', 'Logout failed')},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProfileView(APIView):
    """View user profile"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get current user profile",
        responses={200: UserSerializer()}
    )
    def get(self, request):
        profile_data = AuthService.get_user_profile(request.user)
        return Response(profile_data)


class ProfileUpdateView(APIView):
    """Update user profile information"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Update user profile (full_name, phone_number)",
        request_body=UserProfileUpdateSerializer,
        responses={200: UserSerializer(), 400: 'Bad request'}
    )
    def put(self, request):
        serializer = UserProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.update_user_profile(request.user, serializer.validated_data)
        
        if result['success']:
            # Log activity
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_UPDATE,
                request,
                {'updated_fields': result['updated_fields']}
            )
            
            return Response(UserSerializer(result['user']).data)
        
        return Response(
            {'error': 'Profile update failed'},
            status=status.HTTP_400_BAD_REQUEST
        )


class ProfilePictureUploadView(APIView):
    """Upload or update profile picture"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Upload profile picture",
        request_body=ProfilePictureSerializer,
        responses={200: UserSerializer(), 400: 'Bad request'}
    )
    def post(self, request):
        serializer = ProfilePictureSerializer(
            request.user,
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.upload_profile_picture(
            request.user,
            serializer.validated_data['profile_picture']
        )
        
        if result['success']:
            # Log activity
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_PICTURE_UPLOAD,
                request,
                {'profile_picture': str(request.user.profile_picture) if request.user.profile_picture else None}
            )
            
            return Response(UserSerializer(result['user']).data)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProfilePictureDeleteView(APIView):
    """Delete profile picture"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Delete profile picture",
        responses={200: 'Profile picture deleted', 400: 'No profile picture to delete'}
    )
    def delete(self, request):
        result = AuthService.delete_profile_picture(request.user)
        
        if result['success']:
            # Log activity
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_PICTURE_DELETE,
                request,
                {'action': 'deleted_profile_picture'}
            )
            
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class ChangePasswordView(APIView):
    """Change user password"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Change user password",
        request_body=ChangePasswordSerializer,
        responses={200: 'Password changed successfully', 400: 'Bad request'}
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.change_password(
            user=request.user,
            old_password=serializer.validated_data['old_password'],
            new_password=serializer.validated_data['new_password'],
            confirm_password=serializer.validated_data['confirm_new_password']
        )
        
        if result['success']:
            # Log activity
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PASSWORD_CHANGE,
                request,
                {'action': 'password_changed'}
            )
            
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message'], 'details': result.get('errors', {})},
                status=status.HTTP_400_BAD_REQUEST
            )


class ForgotPasswordView(APIView):
    """Request password reset (sends OTP)"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.AnonRateThrottle]
    
    @swagger_auto_schema(
        operation_description="Request password reset OTP",
        request_body=ForgotPasswordSerializer,
        responses={200: 'OTP sent', 400: 'Bad request'}
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.request_password_reset(
            email=serializer.validated_data['email'],
            request=request
        )
        
        return Response({'message': result['message']}, status=status.HTTP_200_OK)


# ========== OTP Management Views ==========

class RequestOTPView(APIView):
    """Request OTP for password reset or email verification"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.AnonRateThrottle]
    
    @swagger_auto_schema(
        operation_description="Request OTP for password reset or email verification",
        request_body=RequestOTPSerializer,
        responses={200: 'OTP sent', 400: 'Bad request'}
    )
    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        purpose = serializer.validated_data['purpose']
        
        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_active:
                return Response(
                    {'error': 'This account is inactive'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if purpose == 'password_reset':
                result = AuthService.send_otp(user, 'password_reset', send_via='email')
            elif purpose == 'email_verification':
                if user.is_email_verified:
                    return Response(
                        {'error': 'Email already verified'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                result = AuthService.send_otp(user, 'email_verification', send_via='email')
            else:
                result = {'success': False, 'message': 'Invalid purpose'}
            
            if result['success']:
                return Response({'message': result['message']}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': result['message']},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except User.DoesNotExist:
            # Don't reveal if email exists for security
            return Response(
                {'message': 'If the email exists in our system, an OTP has been sent.'},
                status=status.HTTP_200_OK
            )


class VerifyOTPView(APIView):
    """Verify OTP for email verification or password reset"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Verify OTP for email verification",
        request_body=VerifyOTPSerializer,
        responses={200: 'OTP verified', 400: 'Invalid OTP'}
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        purpose = serializer.validated_data['purpose']
        
        try:
            user = User.objects.get(email__iexact=email)
            
            if purpose == 'email_verification':
                result = AuthService.verify_email_with_otp(user, otp, request)
            else:
                result = AuthService.verify_otp(user, otp, purpose)
            
            if result['success']:
                return Response({'message': result['message']}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': result['message']},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class ResetPasswordWithOTPView(APIView):
    """Reset password using OTP"""
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Reset password using OTP",
        request_body=ResetPasswordWithOTPSerializer,
        responses={200: 'Password reset successful', 400: 'Bad request'}
    )
    def post(self, request):
        serializer = ResetPasswordWithOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.reset_password_with_otp(
            email=serializer.validated_data['email'],
            otp=serializer.validated_data['otp'],
            new_password=serializer.validated_data['new_password'],
            confirm_password=serializer.validated_data['confirm_new_password'],
            request=request
        )
        
        if result['success']:
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message'], 'details': result.get('errors', {})},
                status=status.HTTP_400_BAD_REQUEST
            )


class ResendVerificationOTPView(APIView):
    """Resend email verification OTP"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Resend email verification OTP",
        responses={200: 'OTP sent', 400: 'Email already verified'}
    )
    def post(self, request):
        if request.user.is_email_verified:
            return Response(
                {'error': 'Email already verified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = AuthService.send_verification_otp(request.user, request)
        
        if result['success']:
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


# ========== Farmer Upgrade Views ==========

class RequestFarmerUpgradeView(APIView):
    """Request farmer upgrade (sends OTP)"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Request farmer upgrade - sends OTP to email",
        request_body=FarmerUpgradeRequestSerializer,
        responses={200: 'OTP sent', 400: 'Bad request'}
    )
    def post(self, request):
        result = AuthService.request_farmer_upgrade(request.user, request)
        
        if result['success']:
            return Response({'message': result['message']}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class VerifyFarmerUpgradeView(APIView):
    """Verify OTP and upgrade to farmer"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Verify OTP and upgrade to farmer",
        request_body=FarmerUpgradeVerifySerializer,
        responses={200: 'Farmer upgrade successful', 400: 'Bad request'}
    )
    def post(self, request):
        serializer = FarmerUpgradeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = AuthService.verify_farmer_upgrade(
            user=request.user,
            otp=serializer.validated_data['otp'],
            request=request
        )
        
        if result['success']:
            return Response({
                'message': result['message'],
                'role': request.user.role
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )


class FarmerRequestStatusView(APIView):
    """Get farmer upgrade request status"""
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get farmer upgrade request status",
        responses={200: FarmerRequestStatusSerializer()}
    )
    def get(self, request):
        result = AuthService.get_farmer_request_status(request.user)
        return Response(result, status=status.HTTP_200_OK)


# ========== Activity Log View ==========

class UserActivityLogView(generics.ListAPIView):
    """View user activity logs"""
    serializer_class = UserActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AuthService.get_user_activity_logs(self.request.user, limit=100)
    
    @swagger_auto_schema(
        operation_description="Get user activity logs (last 100 entries)",
        responses={200: UserActivityLogSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
