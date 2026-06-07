import re

from django.contrib.auth.password_validation import validate_password
from django.core.validators import EmailValidator
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User, UserActivityLog


class UserSerializer(serializers.ModelSerializer):
    """Base user serializer for read operations"""

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "phone_number",
            "role",
            "profile_picture",
            "is_active",
            "is_email_verified",
            "date_joined",
            "last_login",
        )
        read_only_fields = (
            "id",
            "email",
            "role",
            "is_active",
            "is_email_verified",
            "date_joined",
            "last_login",
        )


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile"""

    class Meta:
        model = User
        fields = ("full_name", "phone_number")

    def validate_full_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Full name cannot be empty")
        if len(value) < 2:
            raise serializers.ValidationError(
                "Full name must be at least 2 characters"
            )
        if len(value) > 255:
            raise serializers.ValidationError(
                "Full name must be less than 255 characters"
            )
        return value.strip()

    def validate_phone_number(self, value):
        if value:
            # Basic phone number validation
            phone_pattern = re.compile(r"^\+?1?\d{9,15}$")
            if not phone_pattern.match(value):
                raise serializers.ValidationError(
                    "Phone number must be in international format (+254712345678)"
                )
        return value


class ProfilePictureSerializer(serializers.ModelSerializer):
    """Serializer for profile picture upload/removal"""

    class Meta:
        model = User
        fields = ("profile_picture",)

    def validate_profile_picture(self, value):
        """Validate profile picture size and type"""
        if value:
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError(
                    "Profile picture cannot exceed 5MB"
                )

            # Check file extension
            allowed_extensions = ["jpg", "jpeg", "png", "gif"]
            ext = value.name.split(".")[-1].lower()
            if ext not in allowed_extensions:
                raise serializers.ValidationError(
                    f"Only {', '.join(allowed_extensions)} formats are allowed"
                )
        return value


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            "email",
            "full_name",
            "phone_number",
            "password",
            "password2",
            "role",
        )
        extra_kwargs = {
            "email": {"required": True, "validators": [EmailValidator()]},
            "full_name": {"required": True},
            "role": {"required": False},
        }

    def validate_email(self, value):
        """Check if email already exists"""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists"
            )
        return value.lower()

    def validate(self, attrs):
        """Validate passwords match"""
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )
        return attrs

    def create(self, validated_data):
        """Create new user"""
        validated_data.pop("password2")
        password = validated_data.pop("password")
        role = validated_data.pop("role", User.Role.CUSTOMER)

        user = User.objects.create_user(
            email=validated_data["email"],
            password=password,
            full_name=validated_data["full_name"],
            phone_number=validated_data.get("phone_number", ""),
            role=role,
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change"""

    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True, write_only=True, validators=[validate_password]
    )
    confirm_new_password = serializers.CharField(
        required=True, write_only=True
    )

    def validate_old_password(self, value):
        """Check if old password is correct"""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect")
        return value

    def validate(self, attrs):
        """Validate new passwords match"""
        if attrs["new_password"] != attrs["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords don't match"}
            )

        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {
                    "new_password": "New password must be different from current password"
                }
            )

        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    """Serializer for forgot password request"""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Check if user exists with this email"""
        try:
            user = User.objects.get(email__iexact=value)
            if not user.is_active:
                raise serializers.ValidationError("This account is inactive")
        except User.DoesNotExist:
            # Don't reveal if email exists for security
            pass
        return value


class ResetPasswordSerializer(serializers.Serializer):
    """Serializer for password reset"""

    token = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True, write_only=True, validators=[validate_password]
    )
    confirm_new_password = serializers.CharField(
        required=True, write_only=True
    )

    def validate(self, attrs):
        """Validate token and passwords"""
        if attrs["new_password"] != attrs["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "Passwords don't match"}
            )

        # Validate token
        token = attrs["token"]
        try:
            user = User.objects.get(reset_password_token=token)
            if user.reset_password_expires < timezone.now():
                raise serializers.ValidationError(
                    {"token": "Password reset token has expired"}
                )
            attrs["user"] = user
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"token": "Invalid password reset token"}
            )

        return attrs


class UserActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for user activity logs"""

    class Meta:
        model = UserActivityLog
        fields = ("id", "activity_type", "ip_address", "details", "created_at")
        read_only_fields = ("id", "created_at")


# ========== OTP and Farmer Upgrade Serializers ==========


class RequestOTPSerializer(serializers.Serializer):
    """Serializer for requesting OTP"""

    email = serializers.EmailField(required=True)
    purpose = serializers.ChoiceField(
        choices=["password_reset", "email_verification"], required=True
    )


class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP"""

    email = serializers.EmailField(required=True)
    otp = serializers.CharField(min_length=6, max_length=6, required=True)
    purpose = serializers.ChoiceField(
        choices=["password_reset", "email_verification", "farmer_upgrade"],
        required=True,
    )


class ResetPasswordWithOTPSerializer(serializers.Serializer):
    """Serializer for resetting password with OTP"""

    email = serializers.EmailField(required=True)
    otp = serializers.CharField(min_length=6, max_length=6, required=True)
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    confirm_new_password = serializers.CharField(
        write_only=True, required=True
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "Passwords don't match"}
            )
        return attrs


class FarmerUpgradeRequestSerializer(serializers.Serializer):
    """Serializer for requesting farmer upgrade"""

    pass


class FarmerUpgradeVerifySerializer(serializers.Serializer):
    """Serializer for verifying farmer upgrade OTP"""

    otp = serializers.CharField(min_length=6, max_length=6, required=True)


class FarmerRequestStatusSerializer(serializers.Serializer):
    """Serializer for farmer request status"""

    has_requested = serializers.BooleanField()
    status = serializers.CharField(allow_null=True)
    requested_at = serializers.DateTimeField(allow_null=True)
