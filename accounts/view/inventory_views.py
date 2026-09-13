from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from accounts.models.stock import StockBatch
from django.db.models import Q, Sum
from openpyxl import Workbook
from django.http import HttpResponse
from accounts.models.org import Branch
from datetime import timedelta
from django.utils import timezone


@login_required
def export_batches_excel(request):
    search = request.GET.get("search", "").strip()
    expiry_filter = request.GET.get("expiry", "")

    batches = (
        StockBatch.objects
        .select_related("product", "branch")
        .order_by("expiry_date")
    )

    if search:
        batches = batches.filter(
            Q(product__name__icontains=search) |
            Q(batch_no__icontains=search)
        )

    if expiry_filter:
        batches = batches.filter(expiry_date__year=expiry_filter)

    wb = Workbook()
    ws = wb.active
    ws.title = "Batch Tracking"

    ws.append([
        "Product",
        "Batch",
        "Expiry Date",
        "Quantity"
    ])

    for batch in batches:
        ws.append([
            str(batch.product),
            batch.batch_no,
            batch.expiry_date.strftime("%Y-%m-%d"),
            float(batch.qty_on_hand)
        ])

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

    response["Content-Disposition"] = (
        'attachment; filename="batch_tracking.xlsx"'
    )

    wb.save(response)

    return response

@login_required
def branch_stock_availability(request):
    today = timezone.localdate()

    # Only un-expired quantities: no expiry date, or expiry date in the future.
    balances = (
        StockBatch.objects
        .filter(qty_on_hand__gt=0)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gt=today))
        .values("product_id", "product__sku", "product__name", "branch_id", "branch__name")
        .annotate(qty=Sum("qty_on_hand"))
    )

    branches = list(Branch.objects.order_by("name"))

    products = {}
    for row in balances:
        product = products.setdefault(row["product_id"], {
            "id": row["product_id"],
            "sku": row["product__sku"],
            "name": row["product__name"],
            "branch_qty": {},
            "total": 0,
        })
        product["branch_qty"][row["branch_id"]] = row["qty"]
        product["total"] += row["qty"]

    rows = sorted(products.values(), key=lambda product: product["name"])

    return render(
        request,
        "accounts/inventory/branch_stock_availability.html",
        {
            "branches": branches,
            "rows": rows,
            "active_branch_id": request.session.get("active_branch_id"),
        },
    )


@login_required
def batch_tracking(request):

    batches = (
        StockBatch.objects
        .select_related("product", "branch")
        .order_by("expiry_date")
    )
    
    branches = (
        Branch.objects
        .order_by("name")
        .distinct()
    )

    return render(
        request,
        "accounts/inventory/batch_tracking.html",
        {
            "batches": batches,
            "branches": branches,
        }
    )



@login_required
def expiry_monitoring(request):

    today = timezone.localdate()

    base_qs = (
        StockBatch.objects
        .select_related(
            "product",
            "branch"
        )
        .filter(
            expiry_date__isnull=False,
            qty_on_hand__gt=0
        )
        .order_by("expiry_date")
    )

    expired = base_qs.filter(
        expiry_date__lt=today
    )

    exp_30 = base_qs.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30)
    )

    exp_90 = base_qs.filter(
        expiry_date__gt=today + timedelta(days=30),
        expiry_date__lte=today + timedelta(days=90)
    )

    exp_180 = base_qs.filter(
        expiry_date__gt=today + timedelta(days=90),
        expiry_date__lte=today + timedelta(days=180)
    )

    safe = base_qs.filter(
        expiry_date__gt=today + timedelta(days=180)
    )

    branches = (
        Branch.objects
        .order_by("name")
    )

    return render(
        request,
        "accounts/inventory/expiry_monitoring.html",
        {
            "branches": branches,
            "expired": expired,
            "exp_30": exp_30,
            "exp_90": exp_90,
            "exp_180": exp_180,
            "safe": safe,
            "expired_count": expired.count(),
            "exp_30_count": exp_30.count(),
            "exp_90_count": exp_90.count(),
            "exp_180_count": exp_180.count(),
            "safe_count": safe.count(),
        }
    )