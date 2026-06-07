import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User

from .choices import (
    EmailTemplateType,
    NotificationCategory,
    NotificationPriority,
    NotificationType,
    SMSTemplateType,
)


class Notification(models.Model):
    """Store all notifications sent to users"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    # Notification details
    notification_type = models.CharField(
        _("type"), max_length=20, choices=NotificationType.choices
    )
    category = models.CharField(
        _("category"), max_length=20, choices=NotificationCategory.choices
    )
    priority = models.CharField(
        _("priority"),
        max_length=10,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )

    # Content
    title = models.CharField(_("title"), max_length=200)
    message = models.TextField(_("message"))
    html_content = models.TextField(_("HTML content"), blank=True)

    # Status
    sent = models.BooleanField(_("sent"), default=False)
    sent_at = models.DateTimeField(_("sent at"), blank=True, null=True)
    delivered = models.BooleanField(_("delivered"), default=False)
    delivered_at = models.DateTimeField(
        _("delivered at"), blank=True, null=True
    )
    read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), blank=True, null=True)

    # Error handling
    error_message = models.TextField(_("error message"), blank=True)
    retry_count = models.PositiveSmallIntegerField(_("retry count"), default=0)

    # Metadata
    template_type = models.CharField(
        _("template type"), max_length=50, blank=True
    )
    reference_id = models.CharField(
        _("reference ID"),
        max_length=100,
        blank=True,
        help_text="Order ID, Payment ID, etc.",
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["sent", "created_at"]),
            models.Index(fields=["notification_type", "category"]),
        ]

    def __str__(self):
        return f"{
            self.notification_type} to {
            self.user.email}: {
            self.title[
                :50]}"

    def mark_as_read(self):
        """Mark notification as read"""
        self.read = True
        self.read_at = timezone.now()
        self.save(update_fields=["read", "read_at"])


class EmailLog(models.Model):
    """Log all emails sent via SendGrid"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to_email = models.EmailField(_("to email"))
    from_email = models.EmailField(
        _("from email"), default=settings.DEFAULT_FROM_EMAIL
    )
    subject = models.CharField(_("subject"), max_length=200)
    template_type = models.CharField(
        _("template type"), max_length=50, choices=EmailTemplateType.choices
    )

    # Content
    html_content = models.TextField(_("HTML content"))
    plain_text_content = models.TextField(_("plain text content"), blank=True)

    # Status
    sendgrid_message_id = models.CharField(
        _("SendGrid message ID"), max_length=100, blank=True
    )
    status = models.CharField(
        _("status"), max_length=50, default="pending"
    )  # pending, sent, failed, delivered, opened, clicked
    delivered_at = models.DateTimeField(
        _("delivered at"), blank=True, null=True
    )
    opened_at = models.DateTimeField(_("opened at"), blank=True, null=True)
    clicked_at = models.DateTimeField(_("clicked at"), blank=True, null=True)

    # Error handling
    error_message = models.TextField(_("error message"), blank=True)

    # Metadata
    reference_id = models.CharField(
        _("reference ID"), max_length=100, blank=True
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("email log")
        verbose_name_plural = _("email logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Email to {self.to_email}: {self.subject}"


class SMSLog(models.Model):
    """Log all SMS messages sent via Africa's Talking"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to_phone = models.CharField(_("to phone"), max_length=15)
    from_phone = models.CharField(_("from phone"), max_length=15, blank=True)
    message = models.TextField(_("message"))
    template_type = models.CharField(
        _("template type"), max_length=50, choices=SMSTemplateType.choices
    )

    # Status
    message_id = models.CharField(_("message ID"), max_length=100, blank=True)
    status = models.CharField(
        _("status"), max_length=50, default="pending"
    )  # pending, sent, failed, delivered
    status_code = models.CharField(_("status code"), max_length=10, blank=True)
    cost = models.DecimalField(
        _("cost"), max_digits=10, decimal_places=4, default=0
    )

    # Error handling
    error_message = models.TextField(_("error message"), blank=True)

    # Metadata
    reference_id = models.CharField(
        _("reference ID"), max_length=100, blank=True
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True)
    delivered_at = models.DateTimeField(
        _("delivered at"), blank=True, null=True
    )

    class Meta:
        verbose_name = _("SMS log")
        verbose_name_plural = _("SMS logs")
        ordering = ["-sent_at"]

    def __str__(self):
        return f"SMS to {self.to_phone}: {self.message[:50]}"
