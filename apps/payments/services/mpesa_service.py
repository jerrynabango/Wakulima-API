import base64
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.orders.models import Order, OrderActivity
from apps.payments.models import Payment, Refund

logger = logging.getLogger(__name__)


class MpesaService:
    """M-Pesa payment integration service"""

    def __init__(self):
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.passkey = settings.MPESA_PASSKEY
        self.shortcode = settings.MPESA_SHORTCODE
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.environment = (
            settings.MPESA_ENVIRONMENT
        )  # 'sandbox' or 'production'

        if self.environment == "sandbox":
            self.base_url = "https://sandbox.safaricom.co.ke"
        else:
            self.base_url = "https://api.safaricom.co.ke"

    def get_access_token(self) -> str:
        """Get M-Pesa API access token with caching"""
        # Check cache first
        cache_key = "mpesa_access_token"
        token = cache.get(cache_key)

        if token:
            return token

        url = (
            f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        )

        auth = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode()

        headers = {"Authorization": f"Basic {auth}"}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            token = data["access_token"]

            # Cache token for 50 minutes (M-Pesa tokens expire in 60 minutes)
            cache.set(cache_key, token, timeout=3000)

            return token
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get M-Pesa access token: {str(e)}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error getting M-Pesa access token: {str(e)}"
            )
            raise

    def stk_push(self, payment: Payment, phone_number: str) -> Dict[str, Any]:
        """Initiate STK Push (Lipa Na M-Pesa Online)"""
        try:
            access_token = self.get_access_token()

            url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.shortcode}{self.passkey}{timestamp}".encode()
            ).decode()

            # Format phone number (remove + or 0, ensure starts with 254)
            original_phone = phone_number
            if phone_number.startswith("+"):
                phone_number = phone_number[1:]
            if phone_number.startswith("0"):
                phone_number = "254" + phone_number[1:]

            payload = {
                "BusinessShortCode": self.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(payment.amount),
                "PartyA": phone_number,
                "PartyB": self.shortcode,
                "PhoneNumber": phone_number,
                "CallBackURL": self.callback_url,
                # Max 12 chars
                "AccountReference": payment.order.order_number[:12],
                "TransactionDesc": f"Payment for Order {payment.order.order_number}",
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                url, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Check for error response
            if data.get("ResponseCode") != "0":
                logger.error(f"M-Pesa STK Push error: {data}")
                return {
                    "success": False,
                    "error": data.get("ResponseDescription", "Unknown error"),
                    "response_code": data.get("ResponseCode"),
                }

            # Store checkout request ID
            payment.mpesa_checkout_request_id = data.get("CheckoutRequestID")
            payment.request_data = data
            payment.save(
                update_fields=["mpesa_checkout_request_id", "request_data"]
            )

            logger.info(
                f"M-Pesa STK Push initiated for payment {payment.id} - Checkout ID: {data.get('CheckoutRequestID')}"
            )

            return {
                "success": True,
                "checkout_request_id": data.get("CheckoutRequestID"),
                "response_code": data.get("ResponseCode"),
                "response_description": data.get("ResponseDescription"),
                "customer_message": data.get("CustomerMessage"),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"M-Pesa STK Push request failed: {str(e)}")
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"M-Pesa STK Push failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def query_status(self, payment: Payment) -> Dict[str, Any]:
        """Query transaction status"""
        if not payment.mpesa_checkout_request_id:
            return {"success": False, "error": "No checkout request ID"}

        try:
            access_token = self.get_access_token()

            url = f"{self.base_url}/mpesa/stkpushquery/v1/query"

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.shortcode}{self.passkey}{timestamp}".encode()
            ).decode()

            payload = {
                "BusinessShortCode": self.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "CheckoutRequestID": payment.mpesa_checkout_request_id,
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                url, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            result_code = data.get("ResultCode")
            result_desc = data.get("ResultDesc")

            # Update payment status based on response
            if result_code == "0":
                # Only update if not already successful
                if payment.status != Payment.PaymentStatus.SUCCESS:
                    payment.status = Payment.PaymentStatus.SUCCESS
                    payment.paid_at = timezone.now()
                    payment.mpesa_result_code = result_code
                    payment.mpesa_result_desc = result_desc
                    payment.response_data = data
                    payment.save()

                    # Update order
                    order = payment.order
                    order.payment_status = Order.PaymentStatus.PAID
                    order.paid_at = timezone.now()

                    if order.order_status == Order.OrderStatus.PENDING:
                        order.order_status = Order.OrderStatus.PROCESSING
                    order.save()

                    # Log activity
                    OrderActivity.objects.create(
                        order=order,
                        activity_type=OrderActivity.ActivityType.PAYMENT_CONFIRMED,
                        description=f"M-Pesa payment confirmed via query - Amount: {payment.amount}",
                        performed_by=payment.user,
                        ip_address="system",
                    )

                    logger.info(
                        f"M-Pesa payment confirmed via query for payment {payment.id}"
                    )
            elif result_code == "1037":
                # User cancelled
                if payment.status != Payment.PaymentStatus.CANCELLED:
                    payment.status = Payment.PaymentStatus.CANCELLED
                    payment.mpesa_result_code = result_code
                    payment.mpesa_result_desc = result_desc
                    payment.save()
                    logger.info(
                        f"M-Pesa payment cancelled for payment {payment.id}"
                    )
            elif result_code not in ["0", "1037"] and result_code is not None:
                # Failed payment
                if payment.status != Payment.PaymentStatus.FAILED:
                    payment.status = Payment.PaymentStatus.FAILED
                    payment.mpesa_result_code = result_code
                    payment.mpesa_result_desc = result_desc
                    payment.save()
                    logger.warning(
                        f"M-Pesa payment failed for payment {payment.id}: {result_desc}"
                    )

            return {
                "success": True,
                "result_code": result_code,
                "result_desc": result_desc,
                "payment_status": payment.status,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"M-Pesa query request failed: {str(e)}")
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"M-Pesa query failed: {str(e)}")
            return {"success": False, "error": str(e)}
