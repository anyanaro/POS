import logging
from datetime import date, datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from accounts.models.integration import BusinessCentralSync
from accounts.models.audit import AuditEvent

logger = logging.getLogger(__name__)


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def queue_sync(entity_type, entity_id, payload):
    payload = _json_value(payload)
    record = BusinessCentralSync.objects.filter(
        entity_type=entity_type,
        entity_id=str(entity_id),
    ).first()
    if record is None:
        record = BusinessCentralSync.objects.create(
            entity_type=entity_type,
            entity_id=str(entity_id),
            payload=payload,
            status="PENDING",
        )
    if record.payload != payload and record.status != "SENT":
        record.payload = payload
        record.status = "PENDING"
        record.save(update_fields=["payload", "status"])
    return record


class BC210Client:
    def __init__(self):
        self.base_url = getattr(settings, "BC210_BASE_URL", "").rstrip("/")
        self.token = getattr(settings, "BC210_ACCESS_TOKEN", "")
        self.timeout = getattr(settings, "BC210_TIMEOUT", 20)

    @property
    def enabled(self):
        return bool(self.base_url and self.token)

    def post(self, resource, payload):
        if not self.enabled:
            raise RuntimeError("Business Central is not configured.")
        response = requests.post(
            f"{self.base_url}/{resource.lstrip('/')}",
            json=payload,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json() if response.content else {}


def send_sync(record):
    client = BC210Client()
    record.attempts += 1
    try:
        response = client.post(record.entity_type.lower(), record.payload)
        record.status = "SENT"
        record.external_id = str(response.get("id", response.get("systemId", "")))
        record.sent_at = timezone.now()
        record.last_error = ""
        record.save(update_fields=["attempts", "status", "external_id", "sent_at", "last_error"])
        AuditEvent.objects.create(
            action="BC_SYNC_SENT",
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            details={"external_id": record.external_id},
        )
        if record.entity_type == "SALE":
            from accounts.models.sales import SalesHeader
            SalesHeader.objects.filter(
                sale_id=record.entity_id,
                posted_to_bc=False,
            ).update(
                posted_to_bc=True,
                posted_to_bc_at=record.sent_at,
            )
        return record
    except Exception as exc:
        logger.exception("Business Central sync failed for %s/%s", record.entity_type, record.entity_id)
        record.status = "FAILED"
        record.last_error = str(exc)
        record.save(update_fields=["attempts", "status", "last_error"])
        AuditEvent.objects.create(
            action="BC_SYNC_FAILED",
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            details={"error": str(exc), "attempts": record.attempts},
        )
        return record
