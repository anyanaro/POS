# accounts/view/views_purchase.py
from decimal import Decimal, ROUND_HALF_UP
import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, EmptyPage
from django.db import transaction
from django.db.models import (
    Sum,
    F,  Q,
    Value,
    DecimalField,
    ExpressionWrapper,
    Max,
)
from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from accounts.models.org import Branch
from accounts.models.product import Product
from accounts.models.stock import StockBatch, StockLedger
from accounts.models.purchase import Supplier, PurchaseHeader, PurchaseLine
import csv
from django.http import HttpResponse
from openpyxl import Workbook
from django.db.models import Sum
from django.db.models.functions import Coalesce, Cast, TruncDate
from django.db.models import Case, When, Value, IntegerField



# ---- helpers ----
def _q4(x):  # 4 dp
    return (Decimal(x or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

def _q2(x):  # 2 dp
    return (Decimal(x or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _active_branch(request):
    bid = request.session.get("active_branch_id")
    return Branch.objects.filter(pk=bid).first() if bid else None


class PurchaseSubmitView(LoginRequiredMixin, View):
    """
    POST /purchases/submit/
    Body:
    {
      "supplier": "ABC Ltd" or null,
      "supplier_id": 3 (optional alternative to supplier name),
      "reference": "INV-001",
      "purchase_date": "YYYY-MM-DD",
      "lines": [
        { "product_id": 1, "qty": 2.5, "buying_cost": 5.7500, "batch_no": "B-01", "expiry_date": "2027-12-31" | null }
      ]
    }
    """
    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        lines = body.get("lines") or []
        if not isinstance(lines, list) or not lines:
            return JsonResponse({"error": "No lines provided."}, status=400)

        supplier_name = (body.get("supplier") or "").strip()
        supplier_id = body.get("supplier_id")
        reference = (body.get("reference") or "").strip()[:120]
        purchase_date = body.get("purchase_date") or timezone.localdate().isoformat()
        try:
            pdate = parse_date(purchase_date) or timezone.localdate()
        except Exception:
            pdate = timezone.localdate()

        branch = _active_branch(request)
        if not branch:
            return JsonResponse({"error": "No active branch in session."}, status=400)

        # Resolve supplier: prefer supplier_id, else by name (optional)
        supplier = None
        if supplier_id:
            supplier = Supplier.objects.filter(pk=supplier_id, active=True).first()
            if not supplier:
                return JsonResponse({"error": "Invalid supplier_id"}, status=404)
        elif supplier_name:
            supplier = Supplier.objects.filter(name__iexact=supplier_name, active=True).first()

        if not supplier:
            return JsonResponse(
                {"error": "Select a supplier before submitting the purchase order."},
                status=400,
            )

        # Validate products and quantities; batches are captured at receipt time.
        product_cache = {}
        for idx, ln in enumerate(lines, start=1):
            pid = ln.get("product_id")
            qty = _q4(ln.get("qty"))
            cost = _q4(ln.get("buying_cost"))

            if not pid:
                return JsonResponse({"error": f"Line {idx}: product_id is required."}, status=400)
            if qty <= 0:
                return JsonResponse({"error": f"Line {idx}: qty must be > 0."}, status=400)
            if cost < 0:
                return JsonResponse({"error": f"Line {idx}: buying_cost cannot be negative."}, status=400)
            if pid not in product_cache:
                prod = Product.objects.filter(pk=pid, active=True).first()
                if not prod:
                    return JsonResponse({"error": f"Line {idx}: product {pid} not found/active."}, status=404)
                product_cache[pid] = prod

        # All-or-nothing
        with transaction.atomic():
            header = PurchaseHeader.objects.create(
                branch=branch,
                created_by=request.user,
                supplier=supplier,
                reference=reference or None,
                purchase_date=pdate,
                total=_q2(0),
                status="DRAFT",
            )

            total_cost = Decimal("0.00")

            for ln in lines:
                pid = ln["product_id"]
                qty = _q4(ln["qty"])
                cost = _q4(ln["buying_cost"])
                line_total = _q4(qty * cost)
                PurchaseLine.objects.create(
                    header=header,
                    product_id=pid,
                    qty=qty,
                    buying_cost=cost,
                    line_total=line_total,
                )

                total_cost += line_total

            header.total = _q2(total_cost)
            header.save(update_fields=["total"])

            return JsonResponse({
                "purchase_id": str(header.purchase_id),
                "total": float(header.total),
                "status": header.status,
            }, status=200)

class PurchaseCreateView(LoginRequiredMixin, View):
    def get(self, request):
        suppliers = Supplier.objects.filter(active=True).order_by("name")
        return render(request, "accounts/purchase.html", {
            "suppliers": suppliers,
        })


class UrgentRequisitionView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "accounts/urgent_requisition.html", {
            "products": Product.objects.filter(active=True).order_by("name"),
        })

    def post(self, request):
        branch = _active_branch(request)
        if not branch:
            messages.error(request, "Select an active branch before submitting an urgent requisition.")
            return redirect("accounts:urgent-requisition")

        product_ids = request.POST.getlist("product_id[]")
        quantities = request.POST.getlist("qty[]")
        lines = []
        for product_id, quantity in zip(product_ids, quantities):
            try:
                qty = _q4(quantity)
            except (TypeError, ValueError):
                qty = Decimal("0")
            if product_id and qty > 0:
                lines.append((product_id, qty))

        if not lines:
            messages.error(request, "Add at least one product with a quantity.")
            return redirect("accounts:urgent-requisition")

        with transaction.atomic():
            purchase = PurchaseHeader.objects.create(
                branch=branch,
                created_by=request.user,
                purchase_date=timezone.localdate(),
                status="DRAFT",
                is_urgent=True,
                total=Decimal("0.00"),
            )
            for product_id, qty in lines:
                PurchaseLine.objects.create(
                    header=purchase,
                    product_id=product_id,
                    qty=qty,
                    buying_cost=None,
                    line_total=None,
                )

        messages.success(request, "Urgent requisition submitted for completion.")
        return redirect("accounts:urgent-purchases")


class UrgentPurchaseListView(LoginRequiredMixin, View):
    def get(self, request):
        branch = _active_branch(request)
        purchases = PurchaseHeader.objects.filter(is_urgent=True).select_related(
            "branch", "supplier"
        ).prefetch_related("lines__product", "goods_receipts")
        if branch:
            purchases = purchases.filter(branch=branch)
        purchases = list(purchases.order_by("-created_at"))
        for purchase in purchases:
            purchase.has_receipts = purchase.goods_receipts.exists()
        return render(request, "accounts/urgent_purchases.html", {
            "purchases": purchases,
        })


class UrgentPurchaseEditView(LoginRequiredMixin, View):
    def get(self, request, purchase_id):
        purchase = get_object_or_404(
            PurchaseHeader.objects.prefetch_related("lines__product"),
            purchase_id=purchase_id,
            is_urgent=True,
        )
        if purchase.goods_receipts.exists():
            messages.warning(
                request,
                "This urgent purchase cannot be modified because it has already been GRNed."
            )
            return redirect("accounts:urgent-purchases")
        return render(request, "accounts/urgent_purchase_edit.html", {
            "purchase": purchase,
            "suppliers": Supplier.objects.filter(active=True).order_by("name"),
        })

    def post(self, request, purchase_id):
        purchase = get_object_or_404(
            PurchaseHeader.objects.prefetch_related("lines"),
            purchase_id=purchase_id,
            is_urgent=True,
        )
        if purchase.goods_receipts.exists():
            messages.warning(
                request,
                "This urgent purchase cannot be modified because it has already been GRNed."
            )
            return redirect("accounts:urgent-purchases")
        supplier = get_object_or_404(
            Supplier,
            pk=request.POST.get("supplier_id"),
            active=True,
        )
        purchase_date = parse_date(request.POST.get("purchase_date") or "")
        if not purchase_date:
            messages.error(request, "Enter a valid purchase date.")
            return redirect("accounts:urgent-purchase-edit", purchase_id=purchase.purchase_id)

        total = Decimal("0.00")
        updates = []
        for line in purchase.lines.all():
            try:
                cost = _q4(request.POST.get(f"cost_{line.id}"))
            except (TypeError, ValueError):
                cost = Decimal("-1")
            if cost < 0:
                messages.error(request, f"Enter a valid unit cost for {line.product}.")
                return redirect("accounts:urgent-purchase-edit", purchase_id=purchase.purchase_id)
            line.buying_cost = cost
            line.line_total = _q4(line.qty * cost)
            total += line.line_total
            updates.append(line)

        purchase.supplier = supplier
        purchase.purchase_date = purchase_date
        purchase.total = _q2(total)
        purchase.status = "DRAFT"
        purchase.save(update_fields=["supplier", "purchase_date", "total", "status"])
        PurchaseLine.objects.bulk_update(updates, ["buying_cost", "line_total"])
        messages.success(request, "Urgent purchase details updated.")
        return redirect("accounts:urgent-purchases")



class InventoryExportExcel(LoginRequiredMixin, View):
    def get(self, request):
        branch = _active_branch(request)

        queryset = (
            StockLedger.objects
            .values(
                "product__id",
                "product__sku",
                "product__name",
                "product__supplier__name",
                "branch__name",
                "branch_id",
            )
            .annotate(
                on_hand=Coalesce(
                    Sum("qty_change"),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                ),

                cost=Coalesce(
                    Max("batch__buying_cost"),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                ),

                value=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("batch__qty_on_hand") *
                            F("batch__buying_cost"),
                            output_field=DecimalField(
                                max_digits=18,
                                decimal_places=2
                            )
                        )
                    ),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                )
            )
            .order_by("product__name")
        )
        if branch:
            queryset = queryset.filter(branch_id=branch.id)

        # Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Inventory"

        # Header row
        ws.append(["SKU", "Name", "Supplier", "Branch", "Qty On Hand", "Value"])

        for row in queryset:
            ws.append([
                row["product__sku"],
                row["product__name"],
                row["product__supplier__name"] or "",
                row["branch__name"],
                float(row["on_hand"] or 0),
                float(row["value"] or 0),
            ])

        # Send XLSX
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="inventory.xlsx"'
        wb.save(response)
        return response

class PurchaseExportExcel(LoginRequiredMixin, View):
    def get(self, request):
        qs = (
            PurchaseHeader.objects
            .select_related("supplier", "branch", "created_by")
            .prefetch_related("lines__product", "lines__batch")
            .order_by("-created_at")
        )

        wb = Workbook()

        # Sheet 1: Purchase Headers
        ws1 = wb.active
        ws1.title = "Purchases"
        ws1.append(["Purchase ID", "Date", "Supplier", "Reference", "Branch", "Total", "Created By"])

        for p in qs:
            ws1.append([
                str(p.purchase_id),
                p.purchase_date.isoformat(),
                p.supplier.name if p.supplier else "",
                p.reference or "",
                p.branch.name,
                float(p.total),
                p.created_by.username,
            ])

        # Sheet 2: Lines
        ws2 = wb.create_sheet("Lines")
        ws2.append([
            "Purchase ID", "SKU", "Name", "Batch", "Expiry",
            "Qty", "Cost", "Line Total"
        ])

        for p in qs:
            for l in p.lines.all():
                ws2.append([
                    str(p.purchase_id),
                    l.product.sku,
                    l.product.name,
                    l.batch.batch_no if l.batch else "",
                    l.batch.expiry_date.isoformat() if (l.batch and l.batch.expiry_date) else "",
                    float(l.qty),
                    float(l.buying_cost or 0),
                    float(l.line_total or 0),
                ])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename=\"purchases.xlsx\"'
        wb.save(response)
        return response


class InventoryExportCSV(LoginRequiredMixin, View):
    def get(self, request):
        # build same queryset used in inventory
        branch = _active_branch(request)
        queryset = (
            StockLedger.objects
            .values(
                "product__id",
                "product__sku",
                "product__name",
                "product__supplier__name",
                "branch__name",
                "branch_id",
            )
            .annotate(
                on_hand=Coalesce(
                    Sum("qty_change"),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                ),

                cost=Coalesce(
                    Max("batch__buying_cost"),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                ),

                value=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("batch__qty_on_hand") *
                            F("batch__buying_cost"),
                            output_field=DecimalField(
                                max_digits=18,
                                decimal_places=2
                            )
                        )
                    ),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                )
            )
            .order_by("product__name")
        )
        if branch:
            queryset = queryset.filter(branch_id=branch.id)

        # CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="inventory.csv"'

        writer = csv.writer(response)
        writer.writerow(["SKU", "Name", "Supplier", "Branch", "Qty On Hand", "Value"])

        for row in queryset:
            writer.writerow([
                row["product__sku"],
                row["product__name"],
                row["product__supplier__name"] or "",
                row["branch__name"],
                row["on_hand"],
                float(row["value"] or 0),
            ])

        return response

class PurchaseExportCSV(LoginRequiredMixin, View):
    def get(self, request):
        qs = (
            PurchaseHeader.objects
            .select_related("supplier", "branch", "created_by")
            .order_by("-created_at")
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="purchases.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Purchase ID",
            "Date",
            "Supplier",
            "Reference",
            "Branch",
            "Total",
            "Created By",
        ])

        for p in qs:
            writer.writerow([
                str(p.purchase_id),
                p.purchase_date.isoformat(),
                p.supplier.name if p.supplier else "",
                p.reference or "",
                p.branch.name,
                float(p.total),
                p.created_by.username,
            ])

        return response
        


class PurchaseDetailView(LoginRequiredMixin, View):
    """
    GET /purchases/<uuid:purchase_id>/
      - HTML receipt (default)
    GET /purchases/<uuid:purchase_id>/?format=json OR Accept: application/json
      - JSON payload
    """
    def get(self, request, purchase_id):
        header = (
            PurchaseHeader.objects
            .select_related(
                "branch",
                "created_by",
                "supplier"
            )
            .prefetch_related(
                "lines__product",
                "lines__batch"
            )
            .filter(purchase_id=purchase_id)
            .first()
        )
        if not header:
            return render(request, "accounts/404.html", status=404)

        lines = list(header.lines.all())
        subtotal = sum(
            ((l.buying_cost or Decimal("0")) * l.qty for l in lines),
            Decimal("0"),
        )
        total = header.total or _q2(subtotal)

        wants_json = (
            request.GET.get("format") == "json"
            or "application/json" in (request.headers.get("Accept", "") or "")
        )
        if wants_json:
            payload = {
                "purchase_id": str(header.purchase_id),
                "status": header.status,
                "branch": getattr(header.branch, "name", None),
                "created_by": getattr(header.created_by, "username", None),
                "supplier": getattr(header.supplier, "name", None) if header.supplier_id else None,
                "reference": header.reference,
                "purchase_date": header.purchase_date.isoformat(),
                "total": float(total),
                "lines": [{
                    "product_id": l.product_id,
                    "sku": getattr(l.product, "sku", None),
                    "name": getattr(l.product, "name", None),
                    "batch_no": getattr(l.batch, "batch_no", None) if l.batch_id else None,
                    "expiry_date": getattr(l.batch, "expiry_date", None) if l.batch_id else None,
                    "qty": float(l.qty),
                    "buying_cost": float(l.buying_cost or 0),
                    "line_total": float(l.line_total or (l.qty * (l.buying_cost or 0))),
                } for l in lines],
            }
            return JsonResponse(payload, status=200)

        context = {
            "header": header,
            "lines": lines,
            "subtotal": subtotal,
            "total": total,
        }
        return render(request, "accounts/purchase_detail.html", context)

    def post(self, request, *_args, **_kwargs):
        return HttpResponseNotAllowed(["GET"])


class PurchaseListView(LoginRequiredMixin, View):
    """
    GET /purchases/?from=YYYY-MM-DD&to=YYYY-MM-DD&q=term&supplier=<id>&ordering=<field>&page=<n>
    ordering: -created_at (default), created_at, -total, total, supplier, reference
    """
    def get(self, request, *args, **kwargs):
        branch = _active_branch(request)
        qs = (PurchaseHeader.objects
              .select_related("supplier", "branch", "created_by"))

        if branch:
            qs = qs.filter(branch=branch)

        dfrom = parse_date(request.GET.get("from") or "")
        dto   = parse_date(request.GET.get("to") or "")
        if dfrom:
            qs = qs.filter(purchase_date__gte=dfrom)
        if dto:
            qs = qs.filter(purchase_date__lte=dto)

        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) |
                Q(supplier__name__icontains=q) |
                Q(purchase_id__icontains=q)
            )

        supplier_id = request.GET.get("supplier")
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
  
        qs = qs.order_by("-purchase_date")


        suppliers = Supplier.objects.filter(active=True).order_by("name")
        context = {
            "purchases": qs,
            "q": q,
            "from": dfrom.isoformat() if dfrom else "",
            "to": dto.isoformat() if dto else "",
            "supplier_id": supplier_id or "",
            "suppliers": suppliers,
        }
        return render(request, "accounts/purchases_list.html", context)