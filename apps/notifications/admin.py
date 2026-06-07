from django.contrib import admin

from apps.notifications.models import EmailLog, Notification, SMSLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "title",
        "notification_type",
        "category",
        "sent",
        "read",
        "created_at",
    )
    list_filter = (
        "notification_type",
        "category",
        "priority",
        "sent",
        "read",
        "created_at",
    )
    search_fields = ("user__email", "user__full_name", "title", "message")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        ("Recipient", {"fields": ("user",)}),
        (
            "Notification Details",
            {
                "fields": (
                    "notification_type",
                    "category",
                    "priority",
                    "title",
                    "message",
                    "html_content",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "sent",
                    "sent_at",
                    "delivered",
                    "delivered_at",
                    "read",
                    "read_at",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "template_type",
                    "reference_id",
                    "metadata",
                    "error_message",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = (
        "to_email",
        "subject",
        "template_type",
        "status",
        "created_at",
    )
    list_filter = ("status", "template_type", "created_at")
    search_fields = ("to_email", "subject", "error_message")
    readonly_fields = ("id", "created_at")


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = (
        "to_phone",
        "message_preview",
        "template_type",
        "status",
        "cost",
        "sent_at",
    )
    list_filter = ("status", "template_type", "sent_at")
    search_fields = ("to_phone", "message")
    readonly_fields = ("id", "sent_at")

    def message_preview(self, obj):
        return (
            obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
        )

    message_preview.short_description = "Message"
