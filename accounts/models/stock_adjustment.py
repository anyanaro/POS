from django.db import models
from django.contrib.auth.models import User
from .stock import StockBatch
from .product import Product
from .org import Branch

class StockAdjustment(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT)

    qty_change = models.DecimalField(max_digits=14, decimal_places=4)
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    created_at = models.DateTimeField(auto_now_add=True)