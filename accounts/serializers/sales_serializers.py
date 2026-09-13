from rest_framework import serializers
from decimal import Decimal
from accounts.models.sales import SalesHeader, SalesLine
from accounts.models.tender import Tender

class SalesLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True)
    expiry_date = serializers.DateField(source="batch.expiry_date", read_only=True)

    class Meta:
        model = SalesLine
        fields = [
            "id", "product", "product_sku", "product_name",
            "batch", "batch_no", "expiry_date",
            "qty", "unit_price", "discount", "line_total", "line_cost"
        ]
        read_only_fields = ["unit_price", "discount", "line_total", "line_cost"]

class TenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tender
        fields = ["id", "tender_type", "amount"]

class SalesHeaderSerializer(serializers.ModelSerializer):
    lines = SalesLineSerializer(many=True, read_only=True)
    tenders = TenderSerializer(many=True, read_only=True)
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    cashier_username = serializers.CharField(source="cashier.username", read_only=True)

    class Meta:
        model = SalesHeader
        fields = [
            "sale_id", "branch", "branch_code", "cashier", "cashier_username",
            "pos_terminal", "total", "tax_total", "status",
            "created_at", "posted_to_bc", "posted_to_bc_at",
            "lines", "tenders"
        ]

# -------- Submit Sale (request payload) --------

class SubmitSaleItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=50)
    qty = serializers.DecimalField(max_digits=12, decimal_places=4)

    def validate_qty(self, value):
        if Decimal(value) <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return value

class SubmitTenderSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[Tender.CASH, Tender.CARD, Tender.MOBILE])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_amount(self, value):
        if Decimal(value) < 0:
            raise serializers.ValidationError("amount cannot be negative")
        return value

class SubmitSaleSerializer(serializers.Serializer):
    terminal = serializers.CharField(max_length=20)
    items = SubmitSaleItemSerializer(many=True)
    tenders = SubmitTenderSerializer(many=True, required=False)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value

# -------- Reverse Sale --------

class ReverseSaleSerializer(serializers.Serializer):
    sale_id = serializers.UUIDField()