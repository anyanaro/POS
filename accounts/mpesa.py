import base64
import json
import requests
from django.conf import settings
from django.core.cache import cache
from datetime import datetime

class MpesaClient:

    def __init__(self):
        self.config = settings.MPESA

    def _get_token(self):
        token = cache.get("mpesa_token")
        if token:
            return token

        url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        resp = requests.get(url, auth=(self.config["CONSUMER_KEY"], self.config["CONSUMER_SECRET"]))
        data = resp.json()

        token = data["access_token"]
        cache.set("mpesa_token", token, 3300)  # 55 min
        return token

    def stk_push(self, phone, amount, reference, description):

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        shortcode = self.config["SHORTCODE"]
        passkey = self.config["PASSKEY"]

        password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.config["CALLBACK_URL"],
            "AccountReference": reference,
            "TransactionDesc": description,
        }

        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        resp = requests.post(url, json=payload, headers=headers)
        return resp.json()

    def query_status(self, checkout_id):
        """Lookup payment result (used by polling /status/)"""

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        shortcode = self.config["SHORTCODE"]
        passkey = self.config["PASSKEY"]
        password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_id,
        }

        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

        resp = requests.post(url, json=payload, headers=headers)
        return resp.json()