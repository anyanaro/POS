# accounts/views/core_views.py
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models.product import Product
from accounts.models.purchase import Supplier
from accounts.models.price_rule import PriceRule
from accounts.models.expense import Expense

from accounts.serializers.core_serializers import (
    ProductSerializer,
    SupplierSerializer,
    PriceRuleSerializer,
    ExpenseSerializer,
)


class ProductListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.filter(active=True).select_related("supplier")
    serializer_class = ProductSerializer


class SupplierListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Supplier.objects.filter(active=True)
    serializer_class = SupplierSerializer


class PriceRuleListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = PriceRule.objects.filter(active=True)
    serializer_class = PriceRuleSerializer


class ExpenseCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)