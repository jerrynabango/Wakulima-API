from abc import ABC, abstractmethod
from typing import Dict, Any
from django.conf import settings
from apps.payments.models import PaymentWebhook
import logging
import hmac
import hashlib
import json

logger = logging.getLogger(__name__)

class BaseWebhookHandler(ABC):
    """Base class for webhook handlers"""
    
    def __init__(self, gateway: str):
        self.gateway = gateway
    
    @abstractmethod
    def validate_signature(self, request_data: Dict[str, Any], signature: str = None, raw_body: bytes = None) -> bool:
        """Validate webhook signature for security"""
        pass
    
    @abstractmethod
    def process_event(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process different webhook event types"""
        pass
    
    def save_webhook_record(self, event_type: str, payload: Dict[str, Any], 
                            processed: bool = False, error: str = None) -> PaymentWebhook:
        """Save incoming webhook to database for audit"""
        return PaymentWebhook.objects.create(
            gateway=self.gateway,
            event_type=event_type,
            payload=payload,
            processed=processed,
            error_message=error or ''
        )
    
    def _verify_signature_with_hmac(self, secret: str, message: str, signature: str) -> bool:
        """Verify HMAC signature"""
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
