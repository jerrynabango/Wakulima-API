from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Optional


class BasePaymentService(ABC):
    """Abstract base class for payment gateways"""

    @abstractmethod
    def initiate_payment(self, payment, request) -> Dict[str, Any]:
        """Initiate payment and return payment URL/instructions"""
        pass

    @abstractmethod
    def verify_payment(self, payment, request) -> Dict[str, Any]:
        """Verify payment status"""
        pass

    @abstractmethod
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming webhook from payment gateway"""
        pass

    @abstractmethod
    def process_refund(
        self, payment, amount: Decimal, reason: str
    ) -> Dict[str, Any]:
        """Process refund for a payment"""
        pass

    @abstractmethod
    def get_payment_status(self, payment) -> str:
        """Get current payment status from gateway"""
        pass
