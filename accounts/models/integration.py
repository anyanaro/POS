from django.db import models


class BusinessCentralSync(models.Model):
    ENTITY_CHOICES = [
        ("SALE", "Sale"),
        ("GRN", "Goods receipt"),
        ("PAYMENT", "Payment"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
    ]

    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    entity_id = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    external_id = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["status", "created_at"]),
        ]
