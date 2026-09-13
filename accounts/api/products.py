# accounts/api/products.py
from rest_framework import serializers, viewsets, permissions, filters
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from decimal import Decimal
from accounts.models import Product, Supplier
from accounts.api.pagination import DefaultPageNumberPagination
from accounts.utils.product_import import import_products as run_product_import
from rest_framework.decorators import action
from rest_framework.response import Response

# NEW IMPORT — safe, no circular import
from accounts.utils.stock import active_branch, average_purchase_cost, sellable_on_hand


class SupplierLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), allow_null=True, required=False
    )
    supplier_name = serializers.SerializerMethodField(read_only=True)

    # NEW: branch-aware stock
    stock = serializers.SerializerMethodField(read_only=True)
    average_buying_cost = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "bc_number", "name", "barcode",
            "buying_cost", "unit_price",
            "reorder_level", "reorder_qty",
            "min_margin_pct", "max_margin_pct", "tax_rate",
            "supplier", "supplier_name",
            "active", "image",
            "stock",       # include in API response
            "average_buying_cost",
        ]

    def get_supplier_name(self, obj):
        return obj.supplier.name if obj.supplier else None

    def get_stock(self, obj):
        request = self.context.get("request")
        branch = active_branch(request)
        branch_id = branch.id if branch else None
        return sellable_on_hand(obj.id, branch_id)

    def get_average_buying_cost(self, obj):
        request = self.context.get("request")
        branch = active_branch(request)
        branch_id = branch.id if branch else None
        return float(average_purchase_cost(obj.id, branch_id))


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("supplier").all().order_by("name")
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Search + ordering + pagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["sku", "bc_number", "name", "barcode", "supplier__name"]
    ordering_fields = [
        "name", "unit_price", "buying_cost",
        "min_margin_pct", "max_margin_pct", "tax_rate", "active"
    ]
    ordering = ["name"]
    pagination_class = DefaultPageNumberPagination

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    # IMPORTANT — give serializer access to request for stock lookup
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        sku = serializer.validated_data.get("sku")
        if sku:
            serializer.validated_data["sku"] = sku.strip().upper()
        serializer.save()

    def perform_update(self, serializer):
        sku = serializer.validated_data.get("sku")
        if sku:
            serializer.validated_data["sku"] = sku.strip().upper()
        serializer.save()

    @action(detail=False, methods=["post"], url_path="import")
    def import_products(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Upload an .xlsx file as file."}, status=400)
        if not upload.name.lower().endswith(".xlsx"):
            return Response({"detail": "Only .xlsx files are supported."}, status=400)
        dry_run = str(request.data.get("dry_run", "false")).lower() in {"1", "true", "yes"}
        result = run_product_import(upload, commit=not dry_run)
        return Response(result, status=400 if result["errors"] else 200)