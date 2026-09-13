from django.db import models
from django.contrib.auth.models import User
from .sales import SalesHeader

class SaleReversal(models.Model):
    header = models.ForeignKey(SalesHeader, on_delete=models.CASCADE, related_name="reversal")
    reversed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    reason = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)