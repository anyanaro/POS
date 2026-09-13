from django.db import models

class Payment(models.Model):
    checkout_id = models.CharField(max_length=100, unique=True)
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="PENDING")   # PENDING, SUCCESS, FAILED
    receipt = models.CharField(max_length=50, null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.checkout_id