from django.db import models
from .purchase import Supplier
from .org import Branch

class VendorLedgerEntry(models.Model):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    TYPES = [
        (DEBIT, "Debit"),
        (CREDIT, "Credit"),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)

    entry_type = models.CharField(max_length=10, choices=TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]