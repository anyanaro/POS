# accounts/models/purchase.py
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User

from .org import Branch
from .product import Product
from .stock import StockBatch

class Supplier(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        blank=True
    )
    bc_number = models.CharField(max_length=100, unique=True)

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=40, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):

        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new and not self.code:

            self.code = f"SUP{self.pk:03d}"

            Supplier.objects.filter(
                pk=self.pk
            ).update(
                code=self.code
            )


class PurchaseHeader(models.Model):
    STATUS_CHOICES = [

        ("DRAFT","Draft"),
        ("APPROVED","Approved"),
        ("SENT","Sent"),
        ("PART_RECEIVED","Part Received"),
        ("RECEIVED","Received"),
        ("INVOICED","Invoiced"),
        ("PAID","Paid"),
        ("CLOSED","Closed"),
    ]
    purchase_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_urgent = models.BooleanField(default=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="purchases")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True, related_name="purchases")
    reference = models.CharField(max_length=120, blank=True, null=True)
    purchase_date = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PUR-{str(self.purchase_id)[:8]} @ {self.branch.code}"


class PurchaseLine(models.Model):
    header = models.ForeignKey(PurchaseHeader, on_delete=models.CASCADE, related_name="lines")
    consolidated_line = models.ForeignKey(
        "accounts.ConsolidatedOrderLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_lines",
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(StockBatch, on_delete=models.SET_NULL, null=True, blank=True)
    qty = models.DecimalField(max_digits=14, decimal_places=4)
    buying_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.product_id} x {self.qty}"