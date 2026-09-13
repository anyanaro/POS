from django.db import models
from django.contrib.auth.models import User
from accounts.models import Branch, Product


class TransferRequestHeader(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending Approval"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("EXECUTED", "Executed"),
    ]

    transfer_no = models.CharField(
        max_length=30,
        unique=True,
        blank=True
    )

    from_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="transfer_requests_out"
    )

    to_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="transfer_requests_in"
    )

    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_transfers"
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_transfers"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    remarks = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    executed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def save(self, *args, **kwargs):

        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new and not self.transfer_no:

            self.transfer_no = f"TR-{self.pk:06d}"

            TransferRequestHeader.objects.filter(
                pk=self.pk
            ).update(
                transfer_no=self.transfer_no
            )

    def __str__(self):

        return self.transfer_no


class TransferRequestLine(models.Model):

    header = models.ForeignKey(
        TransferRequestHeader,
        on_delete=models.CASCADE,
        related_name="lines"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    allocation = models.ForeignKey(
        "accounts.ConsolidatedAllocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfer_lines",
    )

    qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return (
            f"{self.header.transfer_no} - "
            f"{self.product} ({self.qty})"
        )