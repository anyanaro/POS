from rest_framework import serializers
from accounts.models.stock import StockBatch, StockLedger
from accounts.models.product import Product
from accounts.models.org import Branch

class StockBatchSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)

    class Meta:
        model = StockBatch
        fields = [
            "id", "product", "product_sku", "product_name",
            "branch", "branch_code",
            "batch_no", "expiry_date",
            "qty_on_hand", "buying_cost",
        ]

class StockLedgerSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True)

    class Meta:
        model = StockLedger
        fields = [
            "id", "product", "product_sku", "branch", "branch_code",
            "batch", "batch_no", "qty_change", "unit_cost", "reason", "reference", "created_at"
        ]

class StockAdjustmentCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    batch_id = serializers.IntegerField()
    qty_change = serializers.DecimalField(max_digits=14, decimal_places=4)
    reason = serializers.CharField(max_length=300)

    def validate(self, attrs):
        # quick sanity: qty_change not zero
        if attrs["qty_change"] == 0:
            raise serializers.ValidationError("qty_change cannot be 0")
        return attrs

class PhysicalCountSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    batch_id = serializers.IntegerField()
    physical_qty = serializers.DecimalField(max_digits=14, decimal_places=4)