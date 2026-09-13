# accounts/models/procurement.py

import uuid
from django.db import models
from django.contrib.auth.models import User

from .org import Branch
from .product import Product
from .purchase import Supplier, PurchaseHeader


class Requisition(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("APPROVED", "Approved"),
        ("CONSOLIDATED", "Consolidated"),
        ("ORDERED", "Ordered"),
        ("CLOSED", "Closed"),
    ]

    
    requisition_no = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )  
    
    required_date = models.DateField(
            null=True,
            blank=True
        )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT
    )

    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )

    urgent = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
       return self.requisition_no

    
    
class RequisitionLine(models.Model):

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name="lines"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    qty_requested = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )

    qty_approved = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )
    consolidated = models.BooleanField(
        default=False
    )
    approved = models.BooleanField(
        default=False
    )

    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_requisition_lines"
    )
    
class ConsolidatedOrder(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("APPROVED", "Approved"),
        ("CONSOLIDATED", "Consolidated"),
        ("RFQ", "Request for Quote"),
        ("AWARDED", "Awarded"),
        ("ORDERED", "Ordered"),
        ("CLOSED", "Closed"),
    ]

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    
    approved_by = models.ForeignKey(
            User,
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="approved_consolidated_orders"
        )

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    

    
    def __str__(self):
            return f"CO-{self.id}"

    
class ConsolidatedOrderLine(models.Model):

    consolidated_order = models.ForeignKey(
        ConsolidatedOrder,
        on_delete=models.CASCADE,
        related_name="lines"
    )
    
    branch = models.ForeignKey(
        Branch,
        null = True,
        on_delete=models.PROTECT
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    total_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )
    

class ConsolidatedAllocation(models.Model):
    consolidated_line = models.ForeignKey(
        ConsolidatedOrderLine,
        on_delete=models.CASCADE,
        related_name="allocations"
    )

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.PROTECT
    )

    requisition_line = models.ForeignKey(
        RequisitionLine,
        on_delete=models.PROTECT
    )

    allocated_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )

    fulfilled_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )

    transferred_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )
    
    
class SupplierQuotation(models.Model):
    
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("RECEIVED", "Received"),
        ("AWARDED", "Awarded"),
        ("NOT_AWARDED", "Not Awarded"),
        ("ORDERED", "Ordered"),
    ]

    consolidated_order = models.ForeignKey(
        ConsolidatedOrder,
        on_delete=models.PROTECT,
        related_name="rfqs"
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT
    )

    rfq_no = models.CharField(
        max_length=50,
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )
    awarded = models.BooleanField(
        default=False
    )

    
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_supplier_quotations"
    )

    awarded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="awarded_supplier_quotations"
    )

    awarded_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
class SupplierQuotationLine(models.Model):

    quotation = models.ForeignKey(
        SupplierQuotation,
        on_delete=models.CASCADE,
        related_name="lines"
    )

    consolidated_line = models.ForeignKey(
        ConsolidatedOrderLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quotation_lines",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    qty = models.DecimalField(
        max_digits=14,
        decimal_places=4
    )

    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )  
    
    awarded = models.BooleanField(
            default=False)
    

    

    
class ProductCostHistory(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=4
    )

    trade_price = models.DecimalField(
        max_digits=12,
        decimal_places=4
    )

    recorded_at = models.DateTimeField(
        auto_now_add=True
    )

    invoice_no = models.CharField(
        max_length=100
    )