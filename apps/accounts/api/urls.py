from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    CustomTokenObtainPairView,
    FarmerRequestStatusView,
    ForgotPasswordView,
    LogoutView,
    ProfilePictureDeleteView,
    ProfilePictureUploadView,
    ProfileUpdateView,
    ProfileView,
    RegisterView,
    RequestFarmerUpgradeView,
    RequestOTPView,
    ResendVerificationOTPView,
    ResetPasswordWithOTPView,
    UserActivityLogView,
    VerifyFarmerUpgradeView,
    VerifyOTPView,
)

urlpatterns = [
    # Authentication
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Profile Management
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "profile/update/", ProfileUpdateView.as_view(), name="profile_update"
    ),
    path(
        "profile/picture/",
        ProfilePictureUploadView.as_view(),
        name="profile_picture_upload",
    ),
    path(
        "profile/picture/delete/",
        ProfilePictureDeleteView.as_view(),
        name="profile_picture_delete",
    ),
    # Password Management
    path(
        "change-password/",
        ChangePasswordView.as_view(),
        name="change_password",
    ),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot_password",
    ),
    # OTP Operations
    path("otp/request/", RequestOTPView.as_view(), name="request_otp"),
    path("otp/verify/", VerifyOTPView.as_view(), name="verify_otp"),
    path(
        "reset-password/",
        ResetPasswordWithOTPView.as_view(),
        name="reset_password",
    ),
    path(
        "resend-verification/",
        ResendVerificationOTPView.as_view(),
        name="resend_verification",
    ),
    # Farmer Upgrade
    path(
        "farmer/request/",
        RequestFarmerUpgradeView.as_view(),
        name="farmer_request",
    ),
    path(
        "farmer/verify/",
        VerifyFarmerUpgradeView.as_view(),
        name="farmer_verify",
    ),
    path(
        "farmer/status/",
        FarmerRequestStatusView.as_view(),
        name="farmer_status",
    ),
    # Activity Logs
    path(
        "activity-logs/", UserActivityLogView.as_view(), name="activity_logs"
    ),
]
