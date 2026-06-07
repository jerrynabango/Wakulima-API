from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserActivityLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "full_name",
        "role",
        "is_active",
        "is_email_verified",
        "date_joined",
    )
    list_filter = (
        "role",
        "is_active",
        "is_email_verified",
        "is_staff",
        "date_joined",
    )
    search_fields = ("email", "full_name", "phone_number")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("full_name", "phone_number", "profile_picture")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_email_verified",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            _("Important dates"),
            {"fields": ("last_login", "date_joined", "last_login_ip")},
        ),
        (
            _("Farmer Upgrade"),
            {"fields": ("farmer_request_status", "farmer_requested_at")},
        ),
        (
            _("OTP Security"),
            {
                "fields": (
                    "otp_code",
                    "otp_purpose",
                    "otp_expires_at",
                    "otp_attempts",
                    "otp_last_request_at",
                )
            },
        ),
        (
            _("Legacy Reset"),
            {"fields": ("reset_password_token", "reset_password_expires")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "phone_number",
                    "password1",
                    "password2",
                    "role",
                ),
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
        "last_login_ip",
        "otp_code",
        "otp_expires_at",
        "reset_password_token",
        "reset_password_expires",
    )


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "activity_type", "ip_address", "created_at")
    list_filter = ("activity_type", "created_at")
    search_fields = ("user__email", "ip_address")
    readonly_fields = (
        "id",
        "user",
        "activity_type",
        "ip_address",
        "user_agent",
        "details",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
