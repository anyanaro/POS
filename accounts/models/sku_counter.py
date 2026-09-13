# accounts/models/sku_counter.py
from django.db import models

class SkuCounter(models.Model):
    """
    Keeps the last issued number per key.
    Example keys: 'SKU' (global), 'NAK' (per supplier), etc.
    """
    key = models.CharField(max_length=50, unique=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.key}={self.last}"