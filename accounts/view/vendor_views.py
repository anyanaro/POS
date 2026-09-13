# accounts/views/vendor_views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from accounts.serializers.vendor_serializers import VendorPostSerializer
from accounts.serializers.core_serializers import VendorLedgerEntrySerializer
from accounts.services.vendor_ledger_engine import vendor_credit, vendor_debit
from accounts.models.purchase import Supplier
from accounts.models.vendor_ledger import VendorLedgerEntry


class VendorPostEntryView(APIView):
    """
    POST debit/credit
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        data = VendorPostSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        supplier = Supplier.objects.get(id=data.validated_data["supplier_id"])
        entry_type = data.validated_data["entry_type"]
        amount = data.validated_data["amount"]
        ref = data.validated_data.get("reference", "")

        if entry_type == VendorLedgerEntry.CREDIT:
            vendor_credit(supplier, request.active_branch, amount, ref)
        else:
            vendor_debit(supplier, request.active_branch, amount, ref)

        return Response({"status": "ok"}, status=201)


class VendorLedgerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        entries = VendorLedgerEntry.objects.filter(branch=request.active_branch)
        return Response(VendorLedgerEntrySerializer(entries, many=True).data)