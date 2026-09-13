import uuid
from django.db import models
from django.contrib.auth.models import User
from .product import Product
from .stock import StockBatch
from .org import Branch
from accounts.models.Insurance import (
    Insurance,
    InsuranceScheme
)

class SalesHeader(models.Model):

    PAYMENT_METHODS = (
        ("CASH", "Cash"),
        ("MPESA", "M-Pesa"),
        ("INSURANCE", "Insurance"),
        ("CARD", "Card")
    )
    MPESA_MODES = (
        ("STK", "STK Push"),
        ("MANUAL", "Manual"),
    )
    
    sale_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    cashier = models.ForeignKey(User, on_delete=models.PROTECT)
    pos_terminal = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="POSTED")
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_METHODS,default="CASH")
    mpesa_mode = models.CharField(max_length=20,choices=MPESA_MODES,null=True,blank=True,)
    posted_to_bc = models.BooleanField(default=False)
    posted_to_bc_at = models.DateTimeField(null=True, blank=True)
    insurance = models.ForeignKey(
        Insurance,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    insurance_scheme = models.ForeignKey(
        InsuranceScheme,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    member_no = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    
    member_name = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    auth_no = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    def __str__(self):
        return str(self.sale_id)

class SalesLine(models.Model):
    header = models.ForeignKey(SalesHeader, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT, null=True)

    qty = models.DecimalField(max_digits=12, decimal_places=4)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    discount = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=4)
    line_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    selling_price = models.DecimalField(max_digits=12,decimal_places=4,default=0)
    


    