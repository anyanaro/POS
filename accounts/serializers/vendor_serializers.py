from rest_framework import serializers
from decimal import Decimal
from accounts.models.vendor_ledger import VendorLedgerEntry

class VendorPostSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField()
    entry_type = serializers.ChoiceField(choices=[VendorLedgerEntry.DEBIT, VendorLedgerEntry.CREDIT])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_amount(self, value):
        if Decimal(value) <= 0:
            raise serializers.ValidationError("amount must be > 0")
        return value