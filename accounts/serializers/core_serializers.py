from rest_framework import serializers
from accounts.models.product import Product
from accounts.models.purchase import Supplier
from accounts.models.price_rule import PriceRule
from accounts.models.expense import Expense
from accounts.models.vendor_ledger import VendorLedgerEntry
from django.conf import settings

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "code", "bc_number", "name", "contact_person", "email", "phone", "address", "active"]

class ProductSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    image_url = serializers.SerializerMethodField()
    # allow upload via multipart form
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)

    def get_image_url(self, obj):
        if not obj.image:
            return None
        try:
            image_url = obj.image.url
        except (AttributeError, ValueError):
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(image_url)
        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        return f"{site_url}{image_url}" if site_url else image_url

    class Meta:
        model = Product
        fields = [
            "id", "sku", "bc_number", "name", "barcode",
            "buying_cost", "unit_price",
            "min_margin_pct", "max_margin_pct",
            "tax_rate",
            "reorder_level", "reorder_qty",
            "supplier", "supplier_name",
            "active",
            "image", "image_url",
        ]

class PriceRuleSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = PriceRule
        fields = ["id", "product", "product_sku", "percentage", "min_qty", "active"]

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["id", "branch", "date", "category", "amount", "description", "created_by", "created_at"]
        read_only_fields = ["created_by", "created_at"]

class VendorLedgerEntrySerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = VendorLedgerEntry
        fields = ["id", "supplier", "supplier_name", "branch", "entry_type", "amount", "reference", "created_at"]

class StockBalanceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    total_qty = serializers.DecimalField(max_digits=14, decimal_places=4)