# accounts/models/stock.py
from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User 
from .product import Product
from .org import Branch
from django.utils import timezone
from django.core.exceptions import ValidationError

class StockBatch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    batch_no = models.CharField(max_length=50)
    expiry_date = models.DateField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.expiry_date is not None:
            today = timezone.localdate()
            if self.expiry_date <= today:
                raise ValidationError({"expiry_date": "Expiry date must be greater than today."})

    qty_on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    buying_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    

    def __str__(self):
        return f"{self.product.sku} @ {self.branch.code} [{self.batch_no}]"


class StockLedger(models.Model):
    IN = "IN"
    OUT = "OUT"
    REASON_CHOICES = [(IN, "IN"), (OUT, "OUT")]
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    batch = models.ForeignKey(StockBatch, on_delete=models.SET_NULL, null=True, blank=True)
    qty_change = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    reference = models.CharField(max_length=100, blank=True, null=True)
    created_by = models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)