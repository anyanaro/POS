import uuid

from django.db import models
from django.contrib.auth.models import User

from .org import Branch
from .purchase import PurchaseLine, Supplier, PurchaseHeader
from .product import Product


class GoodsReceipt(models.Model):

    RECEIPT_MODES = [
        ("ORIGINAL_BRANCHES", "Allocate to original requisition branches"),
        ("CONSOLIDATED_BRANCH", "Receive at one selected branch"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("RECEIVED", "Received"),
        ("VERIFIED", "Verified"),
    ]

    grn_no = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )

    po = models.ForeignKey(
        PurchaseHeader,
        on_delete=models.PROTECT,
        related_name="goods_receipts"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT
    )

    receipt_mode = models.CharField(
        max_length=30,
        choices=RECEIPT_MODES,
        default="CONSOLIDATED_BRANCH",
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT
    )

    received_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    remarks = models.TextField(
        blank=True,
        null=True
    )

    received_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"GRN-{str(self.grn_no)[:8]}"
    
    
class GoodsReceiptLine(models.Model):

    receipt = models.ForeignKey(
        GoodsReceipt,
        related_name="lines",
        on_delete=models.CASCADE
    )
    
    po_line = models.ForeignKey(
        PurchaseLine,
        on_delete=models.PROTECT,
        related_name="receipts"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    ordered_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )

    received_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )

    invoiced_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    batch_no = models.CharField(
        max_length=100
    )

    expiry_date = models.DateField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.product.name}"


class GoodsReceiptAllocation(models.Model):

    receipt_line = models.ForeignKey(
        GoodsReceiptLine,
        on_delete=models.CASCADE,
        related_name="allocations",
    )

    allocation = models.ForeignKey(
        "accounts.ConsolidatedAllocation",
        on_delete=models.PROTECT,
        related_name="receipt_allocations",
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
    )

    qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )
    
    
    
class SupplierInvoice(models.Model):

    STATUS_CHOICES = [

        ("DRAFT", "Draft"),

        ("POSTED", "Posted"),

        ("SENT_FINANCE", "Sent Finance"),

        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled")
    ]

    invoice_no = models.CharField(
        max_length=100,
        unique=True
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT
    )

    purchase_order = models.ForeignKey(
        PurchaseHeader,
        on_delete=models.PROTECT
    )

    grn = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.PROTECT
    )

    invoice_date = models.DateField()

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    paid_date = models.DateField(
        null=True,
        blank=True
    )
    paid_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="paid_supplier_invoices"
    )


    def __str__(self):
        return self.invoice_no
    

class SupplierInvoiceLine(models.Model):

    invoice = models.ForeignKey(
        SupplierInvoice,
        related_name="lines",
        on_delete=models.CASCADE
    )

    receipt_line = models.ForeignKey(
        GoodsReceiptLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    qty = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )

    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4
    )

    trade_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0
    )

    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    def __str__(self):
        return self.product.name
    
    
class SupplierPayment(models.Model):

    PAYMENT_METHODS = [

        ("BANK", "Bank"),
        ("MPESA", "Mpesa"),

        ("CHEQUE", "Cheque"),

        ("CASH", "Cash"),
    ]

    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.PROTECT
    )

    payment_date = models.DateField()

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS
    )

    reference = models.CharField(
        max_length=100
    )

    paid_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
