import logging

from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics, permissions, status, throttling
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.api.serializers import (
    ChangePasswordSerializer,
    FarmerRequestStatusSerializer,
    FarmerUpgradeRequestSerializer,
    FarmerUpgradeVerifySerializer,
    ForgotPasswordSerializer,
    ProfilePictureSerializer,
    RegisterSerializer,
    RequestOTPSerializer,
    ResetPasswordWithOTPSerializer,
    UserActivityLogSerializer,
    UserProfileUpdateSerializer,
    UserSerializer,
    VerifyOTPSerializer,
)
from apps.accounts.models import User, UserActivityLog
from apps.accounts.services.auth_service import AuthService

logger = logging.getLogger(__name__)


# ========== Helper function for Swagger ==========
def is_swagger_request(view):
    """Check if the request is for Swagger schema generation"""
    return getattr(view, "swagger_fake_view", False)


class RegisterThrottle(throttling.SimpleRateThrottle):
    """Throttle for registration endpoint"""

    scope = "register"

    def get_cache_key(self, request, view):
        if request.method == "POST" and request.data.get("email"):
            return self.cache_format % {
                "scope": self.scope,
                "ident": request.data.get("email"),
            }
        return None


class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]

    @extend_schema(
        operation_id="user_register",
        summary="Register a new user",
        description="Create a new user account. Role can be 'customer' or 'farmer'.",
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(
                description="User created successfully",
                response=UserSerializer,
            ),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request, *args, **kwargs):
        result = AuthService.register_user(request.data)

        if result["success"]:
            AuthService.log_user_activity(
                result["user"],
                UserActivityLog.ActivityType.LOGIN,
                request,
                {"action": "registration"},
            )

            return Response(
                {
                    "user": result["user_data"],
                    "tokens": result["tokens"],
                    "message": result["message"],
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                {
                    "errors": result.get("errors", {}),
                    "message": result["message"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom token obtain view with activity logging"""

    @extend_schema(
        operation_id="user_login",
        summary="Login to get JWT tokens",
        description="Authenticate with email and password to receive access and refresh tokens.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "example": "user@example.com",
                    },
                    "password": {
                        "type": "string",
                        "format": "password",
                        "example": "password123",
                    },
                },
                "required": ["email", "password"],
            }
        },
        responses={
            200: OpenApiResponse(description="Login successful"),
            401: OpenApiResponse(description="Invalid credentials"),
        },
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            email = request.data.get("email")
            try:
                user = User.objects.get(email__iexact=email)
                AuthService.log_login(user, request)
            except User.DoesNotExist:
                pass

        return response


class LogoutView(APIView):
    """Logout user by blacklisting refresh token"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_logout",
        summary="Logout user",
        description="Invalidate refresh token to logout.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "refresh": {
                        "type": "string",
                        "description": "Refresh token",
                    },
                },
                "required": ["refresh"],
            }
        },
        responses={
            205: OpenApiResponse(description="Logout successful"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"error": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = AuthService.blacklist_token(refresh_token)

        if result["success"]:
            AuthService.log_logout(request.user, request)
            return Response(
                {"message": "Successfully logged out"},
                status=status.HTTP_205_RESET_CONTENT,
            )
        else:
            return Response(
                {"error": result.get("error", "Logout failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProfileView(APIView):
    """View user profile"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_profile_get",
        summary="Get user profile",
        description="Retrieve the authenticated user's profile information.",
        responses={200: UserSerializer()},
    )
    def get(self, request):
        profile_data = AuthService.get_user_profile(request.user)
        return Response(profile_data, status=status.HTTP_200_OK)


class ProfileUpdateView(APIView):
    """Update user profile information"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_profile_update",
        summary="Update user profile",
        description="Update full name and phone number.",
        request=UserProfileUpdateSerializer,
        responses={
            200: UserSerializer(),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def put(self, request):
        serializer = UserProfileUpdateSerializer(
            data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        result = AuthService.update_user_profile(
            request.user, serializer.validated_data
        )

        if result["success"]:
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_UPDATE,
                request,
                {"updated_fields": result["updated_fields"]},
            )

            return Response(result["user_data"], status=status.HTTP_200_OK)

        return Response(
            {"error": "Profile update failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ProfilePictureUploadView(APIView):
    """Upload or update profile picture"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="profile_picture_upload",
        summary="Upload profile picture",
        description="Upload a profile picture image file.",
        request=ProfilePictureSerializer,
        responses={
            200: UserSerializer(),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = ProfilePictureSerializer(
            request.user, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        result = AuthService.upload_profile_picture(
            request.user, serializer.validated_data["profile_picture"]
        )

        if result["success"]:
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_PICTURE_UPLOAD,
                request,
                {
                    "profile_picture": result["user_data"].get(
                        "profile_picture"
                    )
                },
            )

            return Response(result["user_data"], status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProfilePictureDeleteView(APIView):
    """Delete profile picture"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="profile_picture_delete",
        summary="Delete profile picture",
        description="Remove the user's profile picture.",
        responses={
            200: OpenApiResponse(description="Profile picture deleted"),
            400: OpenApiResponse(description="No profile picture to delete"),
        },
    )
    def delete(self, request):
        result = AuthService.delete_profile_picture(request.user)

        if result["success"]:
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PROFILE_PICTURE_DELETE,
                request,
                {"action": "deleted_profile_picture"},
            )

            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ChangePasswordView(APIView):
    """Change user password"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_change_password",
        summary="Change password",
        description="Change authenticated user's password.",
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthService.change_password(
            user=request.user,
            old_password=serializer.validated_data["old_password"],
            new_password=serializer.validated_data["new_password"],
            confirm_password=serializer.validated_data["confirm_new_password"],
        )

        if result["success"]:
            AuthService.log_user_activity(
                request.user,
                UserActivityLog.ActivityType.PASSWORD_CHANGE,
                request,
                {"action": "password_changed"},
            )

            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "error": result["message"],
                    "details": result.get("errors", {}),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ForgotPasswordView(APIView):
    """Request password reset (sends OTP)"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.AnonRateThrottle]

    @extend_schema(
        operation_id="user_forgot_password",
        summary="Request password reset OTP",
        description="Send OTP to registered email for password reset.",
        request=ForgotPasswordSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthService.request_password_reset(
            email=serializer.validated_data["email"], request=request
        )

        return Response(
            {"message": result["message"]}, status=status.HTTP_200_OK
        )


class RequestOTPView(APIView):
    """Request OTP for password reset or email verification"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.AnonRateThrottle]

    @extend_schema(
        operation_id="user_request_otp",
        summary="Request OTP",
        description="Request OTP for password reset or email verification.",
        request=RequestOTPSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_active:
                return Response(
                    {"error": "This account is inactive"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if purpose == "password_reset":
                result = AuthService.send_otp(
                    user, "password_reset", send_via="email"
                )
            elif purpose == "email_verification":
                if user.is_email_verified:
                    return Response(
                        {"error": "Email already verified"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                result = AuthService.send_otp(
                    user, "email_verification", send_via="email"
                )
            else:
                result = {"success": False, "message": "Invalid purpose"}

            if result["success"]:
                return Response(
                    {"message": result["message"]}, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"error": result["message"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except User.DoesNotExist:
            return Response(
                {
                    "message": "If the email exists in our system, an OTP has been sent."
                },
                status=status.HTTP_200_OK,
            )


class VerifyOTPView(APIView):
    """Verify OTP for email verification or password reset"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="user_verify_otp",
        summary="Verify OTP",
        description="Verify OTP for email verification or password reset.",
        request=VerifyOTPSerializer,
        responses={
            200: OpenApiResponse(description="OTP verified"),
            400: OpenApiResponse(description="Invalid OTP"),
        },
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        purpose = serializer.validated_data["purpose"]

        try:
            user = User.objects.get(email__iexact=email)

            if purpose == "email_verification":
                result = AuthService.verify_email_with_otp(user, otp, request)
            else:
                result = AuthService.verify_otp(user, otp, purpose)

            if result["success"]:
                return Response(
                    {"message": result["message"]}, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"error": result["message"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )


class ResetPasswordWithOTPView(APIView):
    """Reset password using OTP"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="user_reset_password_otp",
        summary="Reset password with OTP",
        description="Reset password using OTP received via email.",
        request=ResetPasswordWithOTPSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = ResetPasswordWithOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthService.reset_password_with_otp(
            email=serializer.validated_data["email"],
            otp=serializer.validated_data["otp"],
            new_password=serializer.validated_data["new_password"],
            confirm_password=serializer.validated_data["confirm_new_password"],
            request=request,
        )

        if result["success"]:
            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "error": result["message"],
                    "details": result.get("errors", {}),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendVerificationOTPView(APIView):
    """Resend email verification OTP"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_resend_verification_otp",
        summary="Resend verification OTP",
        description="Resend email verification OTP to user's email.",
        responses={
            200: OpenApiResponse(description="OTP sent"),
            400: OpenApiResponse(description="Email already verified"),
        },
    )
    def post(self, request):
        if request.user.is_email_verified:
            return Response(
                {"error": "Email already verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = AuthService.send_verification_otp(request.user, request)

        if result["success"]:
            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RequestFarmerUpgradeView(APIView):
    """Request farmer upgrade (sends OTP)"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="farmer_upgrade_request",
        summary="Request farmer upgrade",
        description="Request to upgrade customer account to farmer. OTP will be sent to email.",
        request=FarmerUpgradeRequestSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        result = AuthService.request_farmer_upgrade(request.user, request)

        if result["success"]:
            return Response(
                {"message": result["message"]}, status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class VerifyFarmerUpgradeView(APIView):
    """Verify OTP and upgrade to farmer"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="farmer_upgrade_verify",
        summary="Verify farmer upgrade",
        description="Verify OTP to complete farmer upgrade.",
        request=FarmerUpgradeVerifySerializer,
        responses={
            200: OpenApiResponse(description="Farmer upgrade successful"),
            400: OpenApiResponse(description="Bad request"),
        },
    )
    def post(self, request):
        serializer = FarmerUpgradeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthService.verify_farmer_upgrade(
            user=request.user,
            otp=serializer.validated_data["otp"],
            request=request,
        )

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "user": result["user_data"],
                    "role": result["user_data"]["role"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )


class FarmerRequestStatusView(APIView):
    """Get farmer upgrade request status"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="farmer_upgrade_status",
        summary="Get farmer upgrade status",
        description="Check current farmer upgrade request status.",
        responses={200: FarmerRequestStatusSerializer()},
    )
    def get(self, request):
        result = AuthService.get_farmer_request_status(request.user)
        return Response(result, status=status.HTTP_200_OK)


class UserActivityLogView(generics.ListAPIView):
    """View user activity logs"""

    serializer_class = UserActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Skip during Swagger schema generation
        if is_swagger_request(self):
            return UserActivityLog.objects.none()
        queryset = AuthService.get_user_activity_logs(self.request.user, limit=100)
        # Ensure we return a queryset, not None
        return queryset if queryset is not None else UserActivityLog.objects.none()

    @extend_schema(
        operation_id="user_activity_logs",
        summary="Get user activity logs",
        description="Retrieve last 100 user activity logs.",
        responses={200: UserActivityLogSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)