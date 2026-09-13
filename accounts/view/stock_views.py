# accounts/views/stock_views.py
from django.http import JsonResponse, HttpResponseNotAllowed
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Q, Sum
from rest_framework.views import View, APIView
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from accounts.serializers.stock_serializers import (
    StockBatchSerializer,
    StockLedgerSerializer,
    StockAdjustmentCreateSerializer,
    PhysicalCountSerializer
)
from accounts.serializers.core_serializers import StockBalanceSerializer
from accounts.services.stock_engine import get_branch_stock_balances
from accounts.services.stock_adjustment_engine import adjust_stock
from accounts.models.stock import StockBatch, StockLedger
from accounts.models.product import Product


class StockBalancesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        balances = get_branch_stock_balances(request.active_branch)
        return Response(StockBalanceSerializer(balances, many=True).data)


class StockBatchListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        batches = StockBatch.objects.filter(branch=request.active_branch)
        return Response(StockBatchSerializer(batches, many=True).data)


class StockLedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        ledger = StockLedger.objects.filter(branch=request.active_branch)
        return Response(StockLedgerSerializer(ledger, many=True).data)


class StockAdjustmentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        serializer = StockAdjustmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = Product.objects.get(id=serializer.validated_data["product_id"])
        batch = StockBatch.objects.get(id=serializer.validated_data["batch_id"])

        adjust_stock(
            product=product,
            branch=request.active_branch,
            batch=batch,
            qty_change=serializer.validated_data["qty_change"],
            reason=serializer.validated_data["reason"],
            user=request.user,
        )

        return Response({"status": "adjusted"}, status=200)


class PhysicalStockCountView(APIView):
    """
    physical_qty → system_qty → generate variance adjustment
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        data = PhysicalCountSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        product = Product.objects.get(id=data.validated_data["product_id"])
        batch = StockBatch.objects.get(id=data.validated_data["batch_id"])
        physical_qty = data.validated_data["physical_qty"]

        system_qty = batch.qty_on_hand
        variance = physical_qty - system_qty

        if variance != 0:
            adjust_stock(
                product=product,
                branch=request.active_branch,
                batch=batch,
                qty_change=variance,
                reason="PHYS COUNT",
                user=request.user,
            )

        return Response({"status": "count_submitted", "variance": str(variance)})



# ==============================
# Helpers
# ==============================
def _active_branch(request):
    bid = request.session.get("active_branch_id")
    return Branch.objects.filter(pk=bid).first() if bid else None

def _q4(x):
    return (Decimal(x or 0)).quantize(Decimal("0.0001"), ROUND_HALF_UP)

def _q2(x):
    return (Decimal(x or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP)


# ==============================
# Purchase Submit
# ==============================
class PurchaseSubmitView(LoginRequiredMixin, View):
    """
    POST /purchases/submit/
    """
    def post(self, request, *args, **kwargs):
        # Parse JSON body
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        lines = body.get("lines") or []
        if not lines:
            return JsonResponse({"error": "No lines provided"}, status=400)

        supplier_id = body.get("supplier_id")
        supplier_name = (body.get("supplier") or "").strip()
        reference = (body.get("reference") or "").strip()[:120]
        purchase_date_raw = body.get("purchase_date") or timezone.localdate().isoformat()
        purchase_date = parse_date(purchase_date_raw) or timezone.localdate()
        today = timezone.localdate()

        branch = _active_branch(request)
        if not branch:
            return JsonResponse({"error": "No active branch in session"}, status=400)

        # Resolve supplier
        supplier = None
        if supplier_id:
            supplier = Supplier.objects.filter(pk=supplier_id, active=True).first()
            if not supplier:
                return JsonResponse({"error": "Invalid supplier_id"}, status=404)
        elif supplier_name:
            supplier = Supplier.objects.filter(name__iexact=supplier_name, active=True).first()

        # Validate lines
        product_cache = {}
        for idx, ln in enumerate(lines, start=1):
            pid = ln.get("product_id")
            qty = _q4(ln.get("qty"))
            cost = _q4(ln.get("buying_cost"))
            batch_no = (ln.get("batch_no") or "").strip()
            expiry = ln.get("expiry_date")

            if not pid:
                return JsonResponse({"error": f"Line {idx}: product_id required"}, status=400)
            if qty <= 0:
                return JsonResponse({"error": f"Line {idx}: qty must be > 0"}, status=400)
            if cost < 0:
                return JsonResponse({"error": f"Line {idx}: buying_cost cannot be negative"}, status=400)
            if not batch_no:
                return JsonResponse({"error": f"Line {idx}: batch_no required"}, status=400)

            if expiry:
                try:
                    exp = parse_date(expiry)
                except Exception:
                    return JsonResponse({"error": f"Line {idx}: invalid expiry date"}, status=400)
                if exp <= today:
                    return JsonResponse({"error": f"Line {idx}: expiry must be > today"}, status=400)

            # Product check
            if pid not in product_cache:
                prod = Product.objects.filter(pk=pid, active=True).first()
                if not prod:
                    return JsonResponse({"error": f"Line {idx}: product {pid} not found"}, status=404)
                product_cache[pid] = prod

        # ========== CREATE PURCHASE ==========
        with transaction.atomic():
            header = PurchaseHeader.objects.create(
                branch=branch,
                created_by=request.user,
                supplier=supplier,
                reference=reference or None,
                purchase_date=purchase_date,
                total=_q2(0),
                status="POSTED"
            )

            total_cost = Decimal("0.00")

            for ln in lines:
                pid = ln["product_id"]
                qty = _q4(ln["qty"])
                cost = _q4(ln["buying_cost"])
                batch_no = ln["batch_no"].strip()
                expiry = ln.get("expiry_date")

                # Create or update batch
                batch, created = StockBatch.objects.get_or_create(
                    product_id=pid,
                    branch_id=branch.id,
                    batch_no=batch_no,
                    expiry_date=expiry,
                    defaults={
                        "qty_on_hand": Decimal("0.0000"),
                        "buying_cost": cost,
                    }
                )

                # Increase stock + update latest cost
                StockBatch.objects.filter(pk=batch.pk).update(
                    qty_on_hand=F("qty_on_hand") + qty,
                    buying_cost=cost
                )

                # Ledger
                StockLedger.objects.create(
                    product_id=pid,
                    branch_id=branch.id,
                    batch_id=batch.pk,
                    qty_change=qty,
                    reason=StockLedger.IN,
                    reference=reference or f"PUR-{header.purchase_id}"
                )

                line_total = qty * cost

                PurchaseLine.objects.create(
                    header=header,
                    product_id=pid,
                    batch=batch,
                    qty=qty,
                    buying_cost=cost,
                    line_total=_q4(line_total)
                )

                total_cost += line_total

            header.total = _q2(total_cost)
            header.save(update_fields=["total"])

            return JsonResponse({
                "purchase_id": str(header.purchase_id),
                "total": float(header.total),
                "status": header.status,
            }, status=200)