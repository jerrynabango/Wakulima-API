import uuid
import os
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

def profile_picture_path(instance, filename):
    """Generate file path for profile pictures"""
    ext = filename.split('.')[-1]
    filename = f"{instance.id}_{uuid.uuid4().hex}.{ext}"
    return os.path.join('profile_pics', filename)


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user"""
        if not email:
            raise ValueError(_('The Email field must be set'))
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email as username"""
    
    class Role(models.TextChoices):
        CUSTOMER = 'customer', _('Customer')
        FARMER = 'farmer', _('Farmer')
        ADMIN = 'admin', _('Admin')
        SUPPORT = 'support', _('Support')
    
    class FarmerRequestStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Verification')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    full_name = models.CharField(_('full name'), max_length=255)
    phone_number = models.CharField(
        _('phone number'),
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^\+?254\d{9}$',
                message=_("Phone number must be in Kenyan format (e.g., +254712345678)")
            )
        ],
        blank=True,
        null=True
    )
    profile_picture = models.ImageField(
        _('profile picture'),
        upload_to=profile_picture_path,
        blank=True,
        null=True,
        help_text=_("Upload a profile picture (max 5MB)")
    )
    role = models.CharField(
        _('role'), 
        max_length=10, 
        choices=Role.choices, 
        default=Role.CUSTOMER
    )
    
    # Farmer upgrade request
    farmer_request_status = models.CharField(
        _('farmer request status'),
        max_length=10,
        choices=FarmerRequestStatus.choices,
        blank=True,
        null=True
    )
    farmer_requested_at = models.DateTimeField(_('farmer requested at'), blank=True, null=True)
    
    # Account status fields
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    is_email_verified = models.BooleanField(_('email verified'), default=False)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    last_login_ip = models.GenericIPAddressField(_('last login IP'), blank=True, null=True)
    
    # OTP fields (5 minutes expiry)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_purpose = models.CharField(max_length=50, blank=True, null=True)  # 'password_reset', 'farmer_upgrade', 'email_verification'
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    otp_last_request_at = models.DateTimeField(blank=True, null=True)
    
    # Password reset token (backward compatibility)
    reset_password_token = models.CharField(max_length=255, blank=True, null=True)
    reset_password_expires = models.DateTimeField(blank=True, null=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']
    
    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.email
    
    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_full_name(self):
        return self.full_name
    
    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email
    
    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER
    
    @property
    def is_farmer(self):
        return self.role == self.Role.FARMER
    
    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN
    
    @property
    def is_support_user(self):
        return self.role == self.Role.SUPPORT
    
    def delete_profile_picture(self):
        """Delete the user's profile picture"""
        if self.profile_picture:
            if os.path.isfile(self.profile_picture.path):
                os.remove(self.profile_picture.path)
            self.profile_picture = None
            self.save(update_fields=['profile_picture'])
            return True
        return False
    
    def can_request_otp(self):
        """Check if user can request a new OTP (max 3 attempts, wait 1 hour)"""
        if self.otp_attempts >= 3:
            if self.otp_last_request_at:
                one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
                if self.otp_last_request_at > one_hour_ago:
                    return False, f"Too many attempts. Please wait {60 - (timezone.now() - self.otp_last_request_at).seconds // 60} minutes"
        return True, "OK"
    
    def reset_otp_attempts(self):
        """Reset OTP attempts after successful verification"""
        self.otp_attempts = 0
        self.otp_code = None
        self.otp_purpose = None
        self.otp_expires_at = None
        self.save(update_fields=['otp_attempts', 'otp_code', 'otp_purpose', 'otp_expires_at'])


class UserActivityLog(models.Model):
    """Log user activities for audit purposes"""
    
    class ActivityType(models.TextChoices):
        LOGIN = 'login', _('Login')
        LOGOUT = 'logout', _('Logout')
        PASSWORD_CHANGE = 'password_change', _('Password Change')
        PASSWORD_RESET = 'password_reset', _('Password Reset')
        PROFILE_UPDATE = 'profile_update', _('Profile Update')
        PROFILE_PICTURE_UPLOAD = 'profile_picture_upload', _('Profile Picture Upload')
        PROFILE_PICTURE_DELETE = 'profile_picture_delete', _('Profile Picture Delete')
        EMAIL_VERIFICATION = 'email_verification', _('Email Verification')
        FARMER_REQUEST = 'farmer_request', _('Farmer Upgrade Request')
        FARMER_UPGRADED = 'farmer_upgraded', _('Farmer Upgraded')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('user activity log')
        verbose_name_plural = _('user activity logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['activity_type']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.created_at}"
