# ============================================
# CLEANED, STABLE, ROLE-SAFE AND UPDATED views.py
# ============================================

from datetime import timedelta, date
from decimal import Decimal
from math import ceil
import csv
import traceback
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Case, When, Sum, F, Q, Value, DecimalField, ExpressionWrapper, Count
)
from django.db.models.functions import Coalesce, Cast, TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.timezone import localdate, localtime
from accounts.models import SaleReversal, SalesHeader
from openpyxl import Workbook
from accounts.utils.barcode import generate_barcode_image
from accounts.utils.restock import branch_restock_suggestions
from accounts.utils.transfer import build_transfer_matrix
from accounts.models.transfer import TransferRequestHeader, TransferRequestLine
from accounts.models.procurement import ConsolidatedAllocation
from accounts.utils.transfer_exec import execute_transfer
from accounts.utils.notify import notify_email, notify_slack
from django.http import JsonResponse
from accounts.utils.transfer_pdf import generate_transfer_pdf
from django.views.decorators.csrf import csrf_exempt
from accounts.utils.stock import average_purchase_cost, on_hand
import json
from django.contrib import messages
from django.shortcuts import redirect
import random
from django.db.models import Max
from django.shortcuts import get_object_or_404
from accounts.models.Insurance import (
    Insurance,
    InsuranceScheme
)
from accounts.mpesa import MpesaClient
from accounts.models import (
    SalesHeader, SalesLine, Product, Branch, StockLedger, StockBatch, Payment
)
from accounts.models.purchase import Supplier
from accounts.models.stock import StockBatch

# Optional models
try:
    from accounts.models import Expense
except Exception:
    Expense = None

try:
    from ai.models import Forecast
except Exception:
    Forecast = None


# ============================================================
#  SHARED DECIMAL HELPERS
# ============================================================

DEC_FIELD = DecimalField(max_digits=18, decimal_places=2)
DEC4_FIELD = DecimalField(max_digits=18, decimal_places=4)
DEC0 = Decimal("0.00")


def dec0_expr():
    """Typed decimal fallback used throughout."""
    return Value(DEC0, output_field=DEC_FIELD)

#  HELPERS
# ============================================================

def _active_branch(request):
    bid = request.session.get("active_branch_id")
    return Branch.objects.filter(pk=bid).first() if bid else None

# ============================================================
#  SAFE ROLE RESOLVER (never throws)
# ============================================================

def get_user_role(user):
    try:
        return user.profile.role
    except Exception:
        return "MANAGER"


@login_required
@csrf_exempt
def stk_push(request):
    data = json.loads(request.body)

    phone = data.get("phone")
    if not phone:
        return JsonResponse(
            {"error": "Phone number required"},
            status=400
        )

    total = sum((i["qty"] * i["unit_price"]) - i.get("discount", 0) for i in data["lines"])

    mpesa = MpesaClient()
    resp = mpesa.stk_push(phone, amount=total, reference="POS SALE", description="Payment for goods")

    if "CheckoutRequestID" not in resp:
        return JsonResponse({"error": resp.get("errorMessage", "MPESA STK Push failed")}, status=400)

    checkout_id = resp["CheckoutRequestID"]

    Payment.objects.create(
        checkout_id=checkout_id,
        phone=phone,
        amount=total,
        status="PENDING"
    )

    return JsonResponse({"checkout_id": checkout_id})
 


def payment_status(request, checkout_id):
    pay = Payment.objects.filter(checkout_id=checkout_id).first()
    if not pay:
        return JsonResponse({"status": "NOT_FOUND"})

    return JsonResponse({"status": pay.status})

@login_required
@csrf_exempt
def mpesa_callback(request):
    data = json.loads(request.body)

    callback = data["Body"]["stkCallback"]
    checkout_id = callback["CheckoutRequestID"]
    result = callback["ResultCode"]

    pay = get_object_or_404(Payment, checkout_id=checkout_id)

    if result == 0:
        items = callback["CallbackMetadata"]["Item"]
        receipt = next((i["Value"] for i in items if i["Name"] == "MpesaReceiptNumber"), None)

        pay.status = "SUCCESS"
        pay.receipt = receipt
        pay.raw = data
        pay.save()

    else:
        pay.status = "FAILED"
        pay.raw = data
        pay.save()

    return JsonResponse({"ok": True})

@login_required
@csrf_exempt
def stock_check(request):
    from accounts.utils.stock import active_branch, sellable_on_hand

    branch = active_branch(request)
    branch_id = branch.id if branch else None

    data = json.loads(request.body)
    lines = data.get("lines", [])

    results = []
    for item in lines:
        p = get_object_or_404(Product, id=item["product_id"])
        available = sellable_on_hand(p.id, branch_id)

        results.append({
            "product_id": p.id,
            "name": p.name,
            "available": float(available),
            "requested": item["qty"],
            "ok": available >= item["qty"],
        })

    return JsonResponse({"items": results})

@login_required
@csrf_exempt
def sales_submit(request):
    from accounts.utils.stock import active_branch, sellable_on_hand

    branch = active_branch(request)
    branch_id = branch.id if branch else None

    data = json.loads(request.body)
    lines = data.get("lines", [])

    if not lines:
        return JsonResponse({"error": "Cart is empty"}, status=400)

    # 🔥 BACKEND STOCK VALIDATION
    for item in lines:
        p = get_object_or_404(Product, id=item["product_id"])
        available = sellable_on_hand(p.id, branch_id)

        if available < Decimal(str(item["qty"])):
            return JsonResponse({
                "error": f"Insufficient stock for {p.name}",
                "product": p.name,
                "available": float(available),
                "requested": item["qty"]
            }, status=400)

# ============================================================
# Bar code
# ============================================================

def barcode_image(request, sku):
    image_data = generate_barcode_image(sku, barcode_type="code128")
    return HttpResponse(image_data, content_type="image/png")



# ============================================================
# Restoke by Branch
# ============================================================
def restock_api(request):
    data = branch_restock_suggestions()
    return JsonResponse({"results": data})


# ============================================================
# Transfer_execute
# ============================================================

@csrf_exempt
def transfer_execute(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    data = json.loads(request.body)

    product_id = data.get("product_id")
    from_branch_id = data.get("from_branch")
    to_branch_id = data.get("to_branch")
    qty = int(data.get("qty", 0))
    reference = data.get("reference")

    if not product_id or not from_branch_id or not to_branch_id or qty <= 0:
        return JsonResponse({"error": "Invalid payload"}, status=400)

    # RUN TRANSFER
    result = execute_transfer(
        product_id=product_id,
        from_branch_id=from_branch_id,
        to_branch_id=to_branch_id,
        qty=qty,
        user=request.user,
        reference=reference
    )

    # STOP IF FAILED
    if "error" in result:
        return JsonResponse(result, status=400)

    # SEND NOTIFICATIONS ONLY IF SUCCESS
    try:
        notify_email(
            subject="Transfer Executed",
            message=f"{result['qty']} units of {result['product']} ({result['sku']}) "
                    f"moved from {result['from']} → {result['to']}.",
            recipients=["aaron.motari@gmail.com"]
        )
    except Exception as e:
        print("Email notification failed:", e)

    try:
        notify_slack(
            f"Transfer completed: {result['qty']} x {result['sku']} "
            f"from {result['from']} to {result['to']}.",
            webhook_url="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
        )
    except Exception as e:
        print("Slack notification failed:", e)

    return JsonResponse(result)



# ============================================================
# Transfer_execute
# ============================================================

@login_required
def branch_stock_api(request, product_id):
    """
    Returns live stock in ALL branches for a given product.
    Used by the modal to display From Stock → To Stock.
    """
    product = Product.objects.filter(pk=product_id).first()
    if not product:
        return JsonResponse({"error": "Product not found"}, status=404)

    from accounts.utils.stock import sellable_on_hand

    data = {}
    for b in Branch.objects.all():
        data[str(b.id)] = float(sellable_on_hand(product_id, b.id))

    return JsonResponse(data)


@login_required
def transfer_available_products(request):
    branch = get_object_or_404(Branch, pk=request.GET.get("branch_id"), active=True)
    today = timezone.localdate()
    products = (
        StockBatch.objects.filter(branch=branch, qty_on_hand__gt=0)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gt=today))
        .values("product_id", "product__sku", "product__name")
        .annotate(available=Sum("qty_on_hand"))
        .order_by("product__name")
    )
    return JsonResponse({
        "results": [
            {
                "id": row["product_id"],
                "label": f"{row['product__sku']} - {row['product__name']}",
                "available": float(row["available"]),
            }
            for row in products
        ]
    })


@login_required
def stock_transfer_suggestions(request):
    today = timezone.localdate()
    since = today - timedelta(days=90)
    branches = list(Branch.objects.filter(active=True).order_by("name"))
    products = list(Product.objects.filter(active=True).order_by("name"))
    suggestions = []

    sellable_batches = (
        StockBatch.objects.filter(qty_on_hand__gt=0)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gt=today))
        .select_related("product", "branch")
        .order_by("product_id", "branch_id", "expiry_date", "batch_no")
    )
    batches_by_product_branch = {}
    stock_by_product_branch = {}
    for batch in sellable_batches:
        key = (batch.product_id, batch.branch_id)
        batches_by_product_branch.setdefault(key, []).append(batch)
        stock_by_product_branch[key] = stock_by_product_branch.get(key, Decimal("0")) + batch.qty_on_hand

    sales_by_product_branch = {
        (row["product_id"], row["header__branch_id"]): row["total"] or Decimal("0")
        for row in SalesLine.objects.filter(
            header__created_at__date__gte=since,
            header__branch__active=True,
        ).values("product_id", "header__branch_id").annotate(total=Sum("qty"))
    }

    for product in products:
        branch_data = []
        for branch in branches:
            stock = stock_by_product_branch.get((product.id, branch.id), Decimal("0"))
            sold = sales_by_product_branch.get((product.id, branch.id), Decimal("0"))
            demand = sold / Decimal("90")
            need = max(Decimal("0"), Decimal(product.reorder_level or 0) - stock)
            target_need = max(need, (demand * Decimal("14")) - stock)
            branch_data.append({
                "branch": branch,
                "stock": stock,
                "demand": demand,
                "need": target_need,
            })

        for destination in branch_data:
            if destination["need"] <= 0:
                continue
            for source in branch_data:
                if source is destination or source["stock"] <= 0:
                    continue
                source_batches = batches_by_product_branch.get(
                    (product.id, source["branch"].id), []
                )
                for batch in source_batches:
                    expiry_days = (
                        (batch.expiry_date - today).days
                        if batch.expiry_date else None
                    )
                    surplus = max(
                        Decimal("0"),
                        batch.qty_on_hand - max(Decimal(product.reorder_level or 0), source["demand"] * Decimal("14")),
                    )
                    expiring_opportunity = (
                        expiry_days is not None
                        and expiry_days <= 90
                        and destination["demand"] > source["demand"]
                    )
                    dead_opportunity = source["demand"] == 0 and destination["demand"] > 0
                    if surplus <= 0 and not expiring_opportunity and not dead_opportunity:
                        continue
                    available = batch.qty_on_hand if (expiring_opportunity or dead_opportunity) else surplus
                    qty = min(available, destination["need"])
                    if qty <= 0:
                        continue
                    if expiring_opportunity:
                        reason = "EXPIRING"
                        detail = "Expiry risk with stronger demand at destination"
                    elif dead_opportunity:
                        reason = "DEAD"
                        detail = "No recent sales at source; destination is moving stock"
                    else:
                        reason = "SURPLUS"
                        detail = "Source stock exceeds reorder/coverage need"
                    suggestions.append({
                        "product_id": product.id,
                        "product": product.name,
                        "sku": product.sku,
                        "from_branch_id": source["branch"].id,
                        "from_branch": source["branch"],
                        "to_branch_id": destination["branch"].id,
                        "to_branch": destination["branch"],
                        "from_stock": source["stock"],
                        "to_stock": destination["stock"],
                        "qty": qty,
                        "reason": reason,
                        "detail": detail,
                        "days_to_expire": f"{expiry_days} days" if expiry_days is not None else None,
                    })
                    break
    return render(request, "accounts/inventory/transfer_suggestions.html", {"suggestions": suggestions})


@login_required
def create_suggested_transfer_requests(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body)
        selected_items = data.get("items") or []
        if not selected_items:
            return JsonResponse({"error": "Select at least one suggestion."}, status=400)

        grouped = {}
        requested_by_source = {}
        for raw_item in selected_items:
            product = get_object_or_404(Product, pk=raw_item.get("product_id"), active=True)
            from_branch = get_object_or_404(Branch, pk=raw_item.get("from_branch_id"), active=True)
            to_branch = get_object_or_404(Branch, pk=raw_item.get("to_branch_id"), active=True)
            quantity = Decimal(str(raw_item.get("qty") or "0"))
            if quantity <= 0:
                raise ValueError("Suggested quantity must be greater than zero.")
            if from_branch.id == to_branch.id:
                raise ValueError("Source and destination branch cannot be the same.")

            group_key = (from_branch.id, to_branch.id)
            group = grouped.setdefault(group_key, {"from_branch": from_branch, "to_branch": to_branch, "items": {}})
            group["items"][product.id] = group["items"].get(product.id, Decimal("0")) + quantity
            stock_key = (from_branch.id, product.id)
            requested_by_source[stock_key] = requested_by_source.get(stock_key, Decimal("0")) + quantity

        from accounts.utils.stock import sellable_on_hand
        for (branch_id, product_id), requested_qty in requested_by_source.items():
            available_qty = sellable_on_hand(product_id, branch_id)
            if requested_qty > available_qty:
                product = Product.objects.get(pk=product_id)
                branch = Branch.objects.get(pk=branch_id)
                raise ValueError(f"Only {available_qty} units of {product.name} are available in {branch.name}.")

        with transaction.atomic():
            created_requests = []
            for group in grouped.values():
                header = TransferRequestHeader.objects.create(
                    from_branch=group["from_branch"],
                    to_branch=group["to_branch"],
                    requested_by=request.user,
                    status="PENDING",
                )
                for product_id, quantity in group["items"].items():
                    TransferRequestLine.objects.create(header=header, product_id=product_id, qty=quantity)
                created_requests.append(header.transfer_no)

        return JsonResponse({"success": True, "created": len(created_requests), "transfer_numbers": created_requests})
    except (TypeError, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)

from django.utils import timezone

@csrf_exempt
def approve_transfer(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST only"},
            status=405
        )

    data = json.loads(request.body)

    req_id = data.get("id")

    tr = (
        TransferRequestHeader.objects
        .prefetch_related(
            "lines",
            "lines__product"
        )
        .filter(id=req_id)
        .first()
    )

    if not tr:

        return JsonResponse(
            {"error": "Not found"},
            status=404
        )

    tr.status = "APPROVED"
    tr.approved_by = request.user
    tr.approved_at = timezone.now()
    tr.save()

    items = ", ".join([
        f"{line.product.name} ({line.qty})"
        for line in tr.lines.all()
    ])

    notify_email(
        subject="Transfer Approved",
        message=(
            f"Transfer {tr.transfer_no} "
            f"approved.\n\n"
            f"Items: {items}"
        ),
        recipients=["manager@example.com"]
    )

    return JsonResponse({
        "ok": True
    })




from django.db import transaction

@csrf_exempt
def execute_approved_transfer(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST only"},
            status=405
        )

    data = json.loads(request.body)

    tr = (
        TransferRequestHeader.objects
        .prefetch_related(
            "lines",
            "lines__product"
        )
        .filter(
            pk=data.get("id"),
            status="APPROVED"
        )
        .first()
    )

    if not tr:
        return JsonResponse(
            {
                "error":
                "Transfer not approved"
            },
            status=400
        )

    try:

        with transaction.atomic():

            for line in tr.lines.all():

                result = execute_transfer(
                    product_id=line.product_id,
                    from_branch_id=tr.from_branch_id,
                    to_branch_id=tr.to_branch_id,
                    qty=line.qty,
                    user=request.user,
                    reference=tr.transfer_no
                )

                if "error" in result:

                    raise Exception(
                        result["error"]
                    )

                if line.allocation_id:
                    ConsolidatedAllocation.objects.filter(
                        pk=line.allocation_id
                    ).update(
                        transferred_qty=F("transferred_qty") + line.qty
                    )

            tr.status = "EXECUTED"
            tr.executed_at = timezone.now()
            tr.save()
            
        notify_email(
            subject="Transfer Executed",
            message=(
                f"Transfer {tr.transfer_no} "
                f"executed successfully."
            ),
            recipients=["aaron.motari@gmail.com"]
        )

        return JsonResponse({
            "success": True
        })

    except Exception as e:

        return JsonResponse(
            {"error": str(e)},
            status=400
        )
        

def transfer_stats_api(request):
    data = (
        TransferRequestHeader.objects
        .extra(select={"day": "DATE(created_at)"})
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    return JsonResponse(list(data), safe=False)  
    
def transfer_approvals(request):

    pending = (
        TransferRequestHeader.objects
        .select_related(
            "from_branch",
            "to_branch",
            "requested_by",
            "approved_by"
        )
        .prefetch_related(
            "lines",
            "lines__product"
        )
        .filter(
            status="PENDING"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/transfer_approvals.html",
        {
            "pending": pending
        }
    )
    
    
@login_required
def transfer_create(request):
    branches = Branch.objects.filter(active=True).order_by("name")
    product_ids_param = request.GET.get("products", "")
    initial_product_ids = [
        int(pid) for pid in product_ids_param.split(",") if pid.strip().isdigit()
    ]
    active_branch_id = request.session.get("active_branch_id")
    from_branch_param = request.GET.get("from_branch", "")
    to_branch_param = request.GET.get("to_branch", "")

    return render(
        request,
        "accounts/transfer_create.html",
        {
            "branches": branches,
            "active_branch_id": active_branch_id,
            "initial_product_ids": initial_product_ids,
            # Source defaults to the requested stock's branch; destination defaults to the user's branch.
            "initial_from_branch_id": int(from_branch_param) if from_branch_param.isdigit() else None,
            "initial_to_branch_id": int(to_branch_param) if to_branch_param.isdigit() else active_branch_id,
        }
    )
    
    
@login_required
def transfer_request(request):

    products = Product.objects.filter(
        active=True
    ).order_by("name")

    branches = Branch.objects.filter(
        active=True
    ).order_by("name")

    allocations = (
        ConsolidatedAllocation.objects
        .select_related(
            "consolidated_line__product",
            "requisition__branch",
        )
        .filter(fulfilled_qty__gt=F("transferred_qty"))
        .order_by("requisition__branch__name", "consolidated_line__product__name")
    )

    return render(
        request,
        "accounts/transfer_request.html",
        {
            "products": products,
            "branches": branches,
            "allocations": allocations,
        }
    )
    
@csrf_exempt
@login_required
def reject_transfer(request):

    data = json.loads(request.body)

    tr = get_object_or_404(
        TransferRequestHeader,
        pk=data["id"]
    )

    tr.status = "REJECTED"
    tr.approved_by = request.user
    tr.approved_at = timezone.now()
    tr.save()

    tr.save()

    return JsonResponse({
        "ok": True
    })
    

@csrf_exempt
@login_required
def create_transfer_request(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST only"},
            status=405
        )

    try:

        data = json.loads(request.body)

        from_branch_id = data.get("from_branch_id")
        to_branch_id = data.get("to_branch_id")
        items = data.get("items", [])

        if not from_branch_id or not to_branch_id:
            return JsonResponse(
                {"error": "Both branches are required"},
                status=400
            )

        if str(from_branch_id) == str(to_branch_id):
            return JsonResponse(
                {
                    "error":
                    "Source and destination branch cannot be the same."
                },
                status=400
            )

        if not items:
            return JsonResponse(
                {"error": "No items selected"},
                status=400
            )

        from_branch = get_object_or_404(Branch, pk=from_branch_id, active=True)
        to_branch = get_object_or_404(Branch, pk=to_branch_id, active=True)
        product_ids = set()

        with transaction.atomic():

            header = TransferRequestHeader.objects.create(
                from_branch_id=from_branch_id,
                to_branch_id=to_branch_id,
                requested_by=request.user,
                status="PENDING"
            )

            for item in items:

                qty = Decimal(str(item.get("qty", 0)))
                product_id = item.get("product_id")

                if qty <= 0:
                    raise ValueError(
                        "Quantity must be greater than zero"
                    )
                if not product_id:
                    raise ValueError("Select a product for every transfer line.")
                if str(product_id) in product_ids:
                    raise ValueError("Add each product only once and adjust its quantity.")
                product_ids.add(str(product_id))
                product = get_object_or_404(Product, pk=product_id, active=True)

                from accounts.utils.stock import sellable_on_hand
                available_stock = sellable_on_hand(product.id, from_branch.id)
                if qty > available_stock:
                    raise ValueError(
                        f"Only {available_stock} units of {product.name} are available in {from_branch.name}."
                    )

                allocation = None
                if item.get("allocation_id"):
                    allocation = get_object_or_404(
                        ConsolidatedAllocation.objects.select_related(
                            "requisition__branch",
                            "consolidated_line",
                        ),
                        pk=item["allocation_id"],
                    )
                    if allocation.requisition.branch_id != int(to_branch_id):
                        raise ValueError("Transfer destination must match the original requisition branch.")
                    available = allocation.fulfilled_qty - allocation.transferred_qty
                    if qty > available:
                        raise ValueError(f"Only {available} remains for this original requisition.")

                TransferRequestLine.objects.create(
                    header=header,
                    product=product,
                    qty=qty,
                    allocation=allocation,
                )

        return JsonResponse({
            "success": True,
            "id": header.id,
            "transfer_no": header.transfer_no
        })

    except Exception as e:

        return JsonResponse(
            {"error": str(e)},
            status=400
        )
    


@login_required
def transfer_dashboard(request):

    pending = TransferRequestHeader.objects.filter(
        status="PENDING"
    ).count()

    approved = TransferRequestHeader.objects.filter(
        status="APPROVED"
    ).count()

    executed = TransferRequestHeader.objects.filter(
        status="EXECUTED"
    ).count()

    return render(
        request,
        "accounts/transfers.html",
        {
            "pending": pending,
            "approved": approved,
            "executed": executed,
        }
    )

def transfer_pdf(request):

    transfer_id = request.GET.get("id")

    tr = get_object_or_404(
        TransferRequestHeader.objects.prefetch_related(
            "lines",
            "lines__product"
        ),
        pk=transfer_id
    )

    lines = []

    for line in tr.lines.all():

        lines.append({
            "sku": line.product.sku,
            "product": line.product.name,
            "qty": line.qty,
        })

    pdf = generate_transfer_pdf({
        "transfer_no": tr.transfer_no,
        "from": tr.from_branch.name,
        "to": tr.to_branch.name,
        "lines": lines,
    })

    response = HttpResponse(
        pdf,
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; '
        f'filename="{tr.transfer_no}.pdf"'
    )

    return response



@csrf_exempt
def transfer_history(request):
    # Base queryset for Transfer Requests
    history = (
        TransferRequestHeader.objects
        .select_related(
            "from_branch",
            "to_branch",
            "requested_by",
            "approved_by"
        )
        .prefetch_related(
            "lines",
            "lines__product"
        )
    )

    # Base queryset for StockLedger
    stock_moves = StockLedger.objects.filter(
        reason__in=["TRANSFER_IN", "TRANSFER_OUT"]
    )

    # -----------------------------------------
    # SEARCH FILTERS
    # -----------------------------------------
    q = request.GET.get("q", "").strip()
    if q:
        history = history.filter(
            Q(lines__product__sku__icontains=q) |
            Q(lines__product__name__icontains=q) |
            Q(from_branch__name__icontains=q) |
            Q(to_branch__name__icontains=q) |
            Q(transfer_no__icontains=q)
        ).distinct()

        stock_moves = stock_moves.filter(
            Q(product__sku__icontains=q) |
            Q(product__name__icontains=q) |
            Q(branch__name__icontains=q)
        )

    # -----------------------------------------
    # STATUS FILTER
    # -----------------------------------------
    status = request.GET.get("status")
    if status:
        history = history.filter(status=status)

    # -----------------------------------------
    # DATE RANGE FILTER
    # -----------------------------------------
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")

    if from_date:
        history = history.filter(created_at__date__gte=from_date)
        stock_moves = stock_moves.filter(created_at__date__gte=from_date)

    if to_date:
        history = history.filter(created_at__date__lte=to_date)
        stock_moves = stock_moves.filter(created_at__date__lte=to_date)

    # -----------------------------------------
    # ORDERING
    # -----------------------------------------
    history = history.order_by("-created_at")
    stock_moves = stock_moves.order_by("-created_at")

    return render(
        request,
        "accounts/transfer_history.html",
        {
            "history": history,
            "stock_moves": stock_moves,
        }
    )

# ============================================================
#  HELPERS
# ============================================================


def _parse_range(request, default_days=30):
    today = localdate()
    dfrom = parse_date(request.GET.get("from") or "")
    dto = parse_date(request.GET.get("to") or "")

    if not dfrom and not dto:
        dfrom = today - timedelta(days=default_days)
        dto = today
    elif dfrom and not dto:
        dto = today
    elif dto and not dfrom:
        dfrom = today - timedelta(days=default_days)

    return dfrom, dto


def _detect_batch_cost_field():
    return "batch__buying_cost"


# ============================================================
#  _on_hand (Decimal‑safe)
# ============================================================

def _on_hand(product_id: int, branch_id: int | None = None) -> int:
    qs = StockLedger.objects.filter(product_id=product_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    val = qs.aggregate(
        v=Coalesce(Sum("qty_change"), Value(0, output_field=DEC_FIELD))
    )["v"] or 0

    return int(val)



# ============================================================
#  DEMAND
# ============================================================

def _avg_daily_demand(product_id, branch_id=None, fallback_days=14, forecast_days=7):
    today = localdate()

    # Try forecast
    try:
        if Forecast:
            fq = Forecast.objects.filter(product_id=product_id, date__gte=today)
            if branch_id:
                fq = fq.filter(branch_id=branch_id)
            vals = [float(r["yhat"]) for r in fq.order_by("date").values("yhat")[:forecast_days]]
            if vals:
                return sum(vals) / len(vals)
    except Exception:
        pass

    # Fallback
    since = today - timedelta(days=fallback_days)
    qs = SalesLine.objects.filter(product_id=product_id, header__created_at__date__gte=since)
    if branch_id:
        qs = qs.filter(header__branch_id=branch_id)

    total_units = qs.aggregate(v=Coalesce(Sum("qty"), dec0_expr()))["v"] or DEC0
    return float(total_units) / max(1, fallback_days)


def stock_cover_days(product_id, branch_id=None, target_days=14):
    on_hand = _on_hand(product_id, branch_id)
    daily = _avg_daily_demand(product_id, branch_id)
    if daily <= 0:
        return None, target_days
    return float(on_hand) / daily, target_days


def _dashboard_report_data(request):
    """Build branch/date-filtered dashboard reports."""
    date_from, date_to = _parse_range(request, default_days=30)
    branch_id = request.GET.get("branch") or ""
    branch = Branch.objects.filter(pk=branch_id).first() if branch_id else None

    batches = StockBatch.objects.filter(qty_on_hand__gt=0).select_related(
        "product", "branch"
    )
    if branch:
        batches = batches.filter(branch_id=branch.id)

    valuation_rows = []
    current_worth = Decimal("0")
    current_units = Decimal("0")
    for batch in batches.order_by("product__name", "branch__name", "batch_no"):
        value = Decimal(batch.qty_on_hand) * Decimal(batch.buying_cost or 0)
        current_worth += value
        current_units += Decimal(batch.qty_on_hand)
        valuation_rows.append({
            "sku": batch.product.sku,
            "name": batch.product.name,
            "branch": batch.branch.name,
            "batch": batch.batch_no,
            "qty": batch.qty_on_hand,
            "unit_cost": batch.buying_cost,
            "value": value,
        })

    sales = SalesLine.objects.filter(
        header__status="POSTED",
        header__created_at__date__range=[date_from, date_to],
    ).select_related("product", "header")
    if branch:
        sales = sales.filter(header__branch_id=branch.id)

    profit_by_product = {}
    for line in sales:
        row = profit_by_product.setdefault(line.product_id, {
            "sku": line.product.sku,
            "name": line.product.name,
            "units": Decimal("0"),
            "revenue": Decimal("0"),
            "cogs": Decimal("0"),
        })
        row["units"] += Decimal(line.qty)
        row["revenue"] += Decimal(line.line_total or 0)
        row["cogs"] += Decimal(line.line_cost or 0) * Decimal(line.qty)

    gross_profit_rows = []
    for row in profit_by_product.values():
        row["gross_profit"] = row["revenue"] - row["cogs"]
        row["margin_pct"] = (
            row["gross_profit"] / row["revenue"] * Decimal("100")
            if row["revenue"] else Decimal("0")
        )
        gross_profit_rows.append(row)
    gross_profit_rows.sort(key=lambda row: row["gross_profit"], reverse=True)

    reorder_rows = []
    for product in Product.objects.filter(active=True).order_by("name"):
        product_batches = StockBatch.objects.filter(
            product_id=product.id,
            qty_on_hand__gt=0,
        )
        if branch:
            product_batches = product_batches.filter(branch_id=branch.id)
        on_hand_qty = product_batches.aggregate(v=Sum("qty_on_hand"))["v"] or Decimal("0")
        reorder_level = Decimal(product.reorder_level or 0)
        if on_hand_qty <= reorder_level:
            reorder_rows.append({
                "sku": product.sku,
                "name": product.name,
                "on_hand": on_hand_qty,
                "reorder_level": reorder_level,
                "reorder_qty": Decimal(product.reorder_qty or 0),
                "shortfall": max(Decimal("0"), reorder_level - on_hand_qty),
                "average_cost": average_purchase_cost(
                    product.id,
                    branch.id if branch else None,
                ),
            })

    reorder_rows.sort(key=lambda row: (row["on_hand"] - row["reorder_level"], row["name"]))
    reorder_configured_count = Product.objects.filter(
        active=True,
        reorder_level__gt=0,
    ).count()
    gross_profit_total = sum((r["gross_profit"] for r in gross_profit_rows), Decimal("0"))
    gross_revenue_total = sum((r["revenue"] for r in gross_profit_rows), Decimal("0"))
    return {
        "report_from": date_from,
        "report_to": date_to,
        "report_branch": branch_id,
        "report_branches": Branch.objects.order_by("name"),
        "valuation_rows": valuation_rows[:200],
        "gross_profit_rows": gross_profit_rows[:200],
        "gross_profit_total": gross_profit_total,
        "gross_revenue_total": gross_revenue_total,
        "gross_margin_pct": (
            gross_profit_total / gross_revenue_total * Decimal("100")
            if gross_revenue_total else Decimal("0")
        ),
        "current_worth": current_worth,
        "current_units": current_units,
        "reorder_rows": reorder_rows[:200],
        "reorder_configured_count": reorder_configured_count,
        "active_product_count": Product.objects.filter(active=True).count(),
    }


# ============================================================
#  reorder_recommendations
# ============================================================

def reorder_recommendations(limit=10, target_days=14, safety=0.15):
    recos = []

    for p in Product.objects.filter(active=True).only("id", "sku", "name")[:200]:
        on_hand = _on_hand(p.id)
        daily = _avg_daily_demand(p.id)

        if daily <= 0:
            continue

        cover = on_hand / daily
        if cover < target_days:
            gap = max(0.0, target_days * daily - on_hand)
            qty = int(ceil(gap * (1 + safety)))

            recos.append({
                "sku": p.sku,
                "name": p.name,
                "on_hand": on_hand,
                "daily_demand": round(daily, 2),
                "cover": round(cover, 1),
                "reco_qty": qty,
            })

    recos.sort(key=lambda x: (x["cover"], -x["reco_qty"]))
    return recos[:limit]



# ============================================================
#  transfer_suggestions
# ============================================================
def transfer_suggestions(request):
    data = build_transfer_matrix(target_cover_days=14)
    return JsonResponse({"results": data})


# ============================================================
#  forecast_vs_actual
# ============================================================

def forecast_vs_actual(days=14):
    today = localdate()
    since = today - timedelta(days=days - 1)

    # ACTUAL DATA
    actual_qs = (
        SalesLine.objects
        .filter(header__created_at__date__range=[since, today])
        .values("header__created_at__date")
        .annotate(units=Coalesce(Sum("qty"), dec0_expr()))
        .order_by("header__created_at__date")
    )
    actual_map = {str(r["header__created_at__date"]): float(r["units"]) for r in actual_qs}

    # PREDICTED DATA
    pred_map = {}
    try:
        if Forecast:
            pred_qs = (
                Forecast.objects
                .filter(date__range=[since, today])
                .values("date")
                .annotate(y=Coalesce(Sum("yhat"), dec0_expr()))
                .order_by("date")
            )
            pred_map = {str(r["date"]): float(r["y"]) for r in pred_qs}
    except Exception:
        pass

    # Labels
    labels = [str(since + timedelta(days=i)) for i in range(days)]

    # SAFE ARRAYS (NO NONE VALUES)
    actual = [actual_map.get(lbl, 0.0) for lbl in labels]
    pred = [pred_map.get(lbl, 0.0) for lbl in labels]   # ← FIXED LINE

    return labels, actual, pred


# ============================================================
#  profit_sparkline
# ============================================================

def profit_sparkline(days=14):
    today = localdate()
    since = today - timedelta(days=days - 1)

    # Revenue
    rev_qs = (
        SalesHeader.objects
        .filter(created_at__date__range=[since, today], status="POSTED")
        .values("created_at__date")
        .annotate(revenue=Coalesce(Sum("total"), dec0_expr()))
        .order_by("created_at__date")
    )
    rev = {str(r["created_at__date"]): float(r["revenue"]) for r in rev_qs}

    # COGS
    line_value = ExpressionWrapper(
        F("qty") * Coalesce(F("product__buying_cost"), dec0_expr()),
        output_field=DEC_FIELD
    )
    cogs_qs = (
        SalesLine.objects
        .filter(header__created_at__date__range=[since, today], header__status="POSTED")
        .values("header__created_at__date")
        .annotate(cogs=Coalesce(Sum(line_value), dec0_expr()))
        .order_by("header__created_at__date")
    )
    cogs = {str(r["header__created_at__date"]): float(r["cogs"]) for r in cogs_qs}

    labels = [str(since + timedelta(days=i)) for i in range(days)]
    values = [max(0.0, rev.get(lbl, 0.0) - cogs.get(lbl, 0.0)) for lbl in labels]

    return labels, values

# ============================================================
# 30‑DAY REVENUE + PROFIT TREND
# ============================================================

def trend_30_days(days=30):
    today = localdate()
    since = today - timedelta(days=days-1)

    # Revenue per day
    rev_qs = (
        SalesHeader.objects
        .filter(created_at__date__range=[since, today], status="POSTED")
        .values("created_at__date")
        .annotate(revenue=Coalesce(Sum("total"), dec0_expr()))
        .order_by("created_at__date")
    )
    rev_map = {str(r["created_at__date"]): float(r["revenue"]) for r in rev_qs}

    # Profit per day
    line_value = ExpressionWrapper(
        F("qty") * Coalesce(F("product__buying_cost"), dec0_expr()),
        output_field=DEC_FIELD
    )
    cogs_qs = (
        SalesLine.objects
        .filter(header__created_at__date__range=[since, today], header__status="POSTED")
        .values("header__created_at__date")
        .annotate(cogs=Coalesce(Sum(line_value), dec0_expr()))
        .order_by("header__created_at__date")
    )
    cogs_map = {str(r["header__created_at__date"]): float(r["cogs"]) for r in cogs_qs}

    labels = [str(since + timedelta(days=i)) for i in range(days)]
    revenue = [rev_map.get(lbl, 0.0) for lbl in labels]
    profit = [max(0.0, rev_map.get(lbl, 0.0) - cogs_map.get(lbl, 0.0)) for lbl in labels]

    return labels, revenue, profit


# ============================================================
# 7‑DAY BRANCH FORECAST (simple weighted extrapolation)
# ============================================================

def forecast_7_day():
    today = localdate()
    last_14 = today - timedelta(days=13)

    qs = (
        SalesHeader.objects
        .filter(created_at__date__range=[last_14, today], status="POSTED")
        .values("branch__name")
        .annotate(total=Coalesce(Sum("total"), dec0_expr()))
        .order_by("branch__name")
    )

    # Simple average → forecast straight-line
    labels = [str(today + timedelta(days=i)) for i in range(1, 8)]

    series = []
    for r in qs:
        avg_daily = float(r["total"]) / 14
        series.append({
            "label": r["branch__name"] or "Unknown",
            "data": [round(avg_daily, 2)] * 7,
        })

    return labels, series


# ============================================================
# FREQUENTLY BOUGHT TOGETHER (last 30 days)
# ============================================================

def frequently_bought_together(days=30, limit=10):
    today = localdate()
    since = today - timedelta(days=days)

    # Build pairs per sale
    from collections import defaultdict
    per_sale = defaultdict(set)

    qs = (
        SalesLine.objects
        .filter(header__created_at__date__gte=since)
        .values("header_id", "product_id", "product__sku", "product__name")
    )

    for r in qs:
        per_sale[r["header_id"]].add(
            (r["product_id"], r["product__sku"], r["product__name"])
        )

    from collections import Counter
    pair_counter = Counter()

    for sale_id, products in per_sale.items():
        products = list(products)
        if len(products) < 2:
            continue

        for i in range(len(products)):
            for j in range(i + 1, len(products)):
                a = products[i]
                b = products[j]
                key = (a, b)
                pair_counter[key] += 1

    results = []
    for ((id_a, sku_a, name_a), (id_b, sku_b, name_b)), count in pair_counter.most_common(limit):
        results.append({
            "sku_a": sku_a,
            "name_a": name_a,
            "sku_b": sku_b,
            "name_b": name_b,
            "count": count,
        })

    return results


# ============================================================
# GROSS MARGIN (last 30 days)
# ============================================================

def gross_margin(days=30):
    today = localdate()
    since = today - timedelta(days=days)

    revenue = (
        SalesHeader.objects
        .filter(created_at__date__range=[since, today], status="POSTED")
        .aggregate(val=Coalesce(Sum("total"), dec0_expr()))["val"]
    ) or DEC0

    line_value = ExpressionWrapper(
        F("qty") * Coalesce(F("product__buying_cost"), dec0_expr()),
        output_field=DEC_FIELD
    )
    cogs = (
        SalesLine.objects
        .filter(header__created_at__date__range=[since, today], header__status="POSTED")
        .aggregate(val=Coalesce(Sum(line_value), dec0_expr()))["val"]
    ) or DEC0

    profit = revenue - cogs
    gm_pct = (profit / revenue * 100) if revenue > 0 else 0

    return {
        "revenue": float(revenue),
        "cogs": float(cogs),
        "profit": float(profit),
        "gm_pct": round(float(gm_pct), 1),
    }


# ============================================================
# INVENTORY HEALTH METRIC
# ============================================================

def inventory_health():
    low = (
        StockLedger.objects
        .values("product_id", "branch_id")
        .annotate(on_hand=Coalesce(Sum("qty_change"), dec0_expr()))
        .filter(on_hand__lte=5)
        .count()
    )
    out_of_stock = (
        StockLedger.objects
        .values("product_id", "branch_id")
        .annotate(on_hand=Coalesce(Sum("qty_change"), dec0_expr()))
        .filter(on_hand__lte=0)
        .count()
    )
    dead = (
        StockLedger.objects
        .values("product_id", "branch_id")
        .annotate(total=Coalesce(Sum("qty_change"), dec0_expr()))
        .filter(total=0)
        .count()
    )

    # Simple weighted health score
    score = max(0, 100 - (low * 1.2 + out_of_stock * 2 + dead * 0.5))
    score = min(100, int(score))

    return {
        "low_stock": low,
        "stockouts": out_of_stock,
        "dead_stock": dead,
        "health_score": score,
    }



# ============================================================
# AI INSIGHTS (rule-based, safe)
# ============================================================

def ai_insights(context):
    insights = []

    total_sales = context.get("total_sales", 0)
    top5 = context.get("top5", [])
    low_stock_count = context.get("low_stock_count", 0)
    avg_risk = context.get("avg_risk", 0)
    pf_values = context.get("pf_values", [])
    chart_values = context.get("chart_values", [])
    branch_comp = context.get("branch_comp", [])
    risk_scores = context.get("risk_scores", [])

    # ---------------------------------------------------
    # 1. Revenue / Sales Insights
    # ---------------------------------------------------

    if total_sales > 0 and top5:
        insights.append(
            f"30‑day revenue is {total_sales:,.2f}, driven primarily by {top5[0]['product__name']}."
        )

    if total_sales > 50000:
        insights.append("Revenue is strong this month — above the 50K threshold.")

    if total_sales < 5000:
        insights.append("Revenue is unusually low this month — consider reviewing sales activity.")

    # ---------------------------------------------------
    # 2. Profit Insights
    # ---------------------------------------------------

    if pf_values and sum(pf_values[-7:]) <= 0:
        insights.append("Profit has been flat or negative over the last week.")

    if pf_values and max(pf_values) > 2 * (sum(pf_values)/len(pf_values)):
        insights.append("Profit shows a spike — investigate which products drove it.")

    # ---------------------------------------------------
    # 3. Stock Insights
    # ---------------------------------------------------

    if low_stock_count > 20:
        insights.append("Large number of products are critically low — immediate restock recommended.")
    elif low_stock_count > 10:
        insights.append("Multiple products are low on stock — review replenishment levels.")

    # ---------------------------------------------------
    # 4. Branch Performance
    # ---------------------------------------------------

    if avg_risk > 60:
        insights.append("Branch risk is high — monitor stockouts and slow-moving goods closely.")

    if branch_comp:
        worst = min(branch_comp, key=lambda x: x["revenue"])
        best = max(branch_comp, key=lambda x: x["revenue"])
        insights.append(
            f"Best-performing branch: {best['branch__name']} ({best['revenue']:,.2f}). "
            f"Lowest-performing: {worst['branch__name']} ({worst['revenue']:,.2f})."
        )

    # ---------------------------------------------------
    # 5. Trend Insights (Sales Sparkline)
    # ---------------------------------------------------

    if chart_values:
        if len(chart_values) >= 7:
            past = chart_values[-7]
            current = chart_values[-1]
            if current > past:
                insights.append("Sales trend is moving upward compared to last week.")
            elif current < past:
                insights.append("Sales this week are lower than the previous week.")
            else:
                insights.append("Sales are flat compared to last week.")
        else:
            insights.append("Not enough history to determine weekly sales trend.")

    # ---------------------------------------------------
    # 6. Risk Score Insights
    # ---------------------------------------------------

    if risk_scores:
        risky = [r for r in risk_scores if r["score"] > 70]
        if risky:
            insights.append(f"{len(risky)} branches are high risk (score > 70).")

    # ---------------------------------------------------
    # 7. Inventory Health / Dead Stock
    # ---------------------------------------------------

    inv = context.get("inv", None)
    if inv and inv.get("dead_stock", 0) > 0:
        insights.append(f"{inv['dead_stock']} items have zero movement — consider clearance strategy.")

    # ---------------------------------------------------
    # 8. Forecast Deviation
    # ---------------------------------------------------

    fc_actual = context.get("fc_actual", [])
    fc_pred = context.get("fc_pred", [])

    if fc_actual and fc_pred:
        diffs = [abs(a - p) for a, p in zip(fc_actual, fc_pred)]
        avg_diff = sum(diffs) / len(diffs)

        if avg_diff > 10:
            insights.append("Large deviation between forecast and actual units — forecasting model may need tuning.")
        elif avg_diff < 3:
            insights.append("Forecast closely matches actuals — model accuracy appears good.")

    return insights

def cashier_leaderboard(days=30, limit=5):
    dto = localdate()
    dfrom = dto - timedelta(days=days-1)

    qs = (
        SalesHeader.objects
        .filter(created_at__date__range=[dfrom, dto], status="POSTED")
        .annotate(
            cashier_name=Coalesce(F("cashier__username"), Value("Unknown"))
        )
        .values("cashier_name")
        .annotate(
            orders=Count("sale_id"),
            revenue=Coalesce(Sum("total"), dec0_expr())
        )
        .order_by("-revenue")[:limit]
    )

    out = []
    for r in qs:
        orders = int(r["orders"] or 0)
        revenue = float(r["revenue"] or 0)
        aov = revenue / orders if orders > 0 else 0
        out.append({
            "cashier": r["cashier_name"],
            "orders": orders,
            "revenue": round(revenue, 2),
            "aov": round(aov, 2),
        })
    return out


# ============================================================
#  branch_leaderboard (stable grouping)
# ============================================================

def branch_leaderboard(limit=5):
    today = localdate()
    qs = (
        SalesHeader.objects
        .filter(created_at__date=today, status="POSTED")
        .values("branch_id")
        .annotate(
            branch_name=Coalesce(F("branch__name"), Value("Unassigned")),
            revenue=Coalesce(Sum("total"), dec0_expr(), output_field=DEC_FIELD),
        )
        .order_by("-revenue")[:limit]
    )
    return list(qs)


# ============================================================
#  _stock_value_sum, _total_sales_amount, _sales_timeseries
# ============================================================

def _stock_value_sum() -> Decimal:
    cost_field = _detect_batch_cost_field()
    qty_dec = Cast(F("qty_change"), output_field=DEC_FIELD)

    if cost_field:
        line_value = ExpressionWrapper(qty_dec * Coalesce(F(cost_field), dec0_expr()), output_field=DEC_FIELD)
        agg = (
            StockLedger.objects
            .annotate(line_value=line_value)
            .aggregate(v=Coalesce(Sum("line_value"), dec0_expr()))["v"]
        )
        return agg or DEC0

    # fallback
    line_value = ExpressionWrapper(qty_dec * Coalesce(F("product__buying_cost"), dec0_expr()), output_field=DEC_FIELD)
    agg = (
        StockLedger.objects
        .annotate(line_value=line_value)
        .aggregate(v=Coalesce(Sum("line_value"), dec0_expr()))["v"]
    )
    return agg or DEC0


def _total_sales_amount(days=30) -> Decimal:
    today = localdate()
    since = today - timedelta(days=days)
    return (
        SalesHeader.objects
        .filter(created_at__date__gte=since)
        .aggregate(total=Coalesce(Sum("total"), dec0_expr()))["total"]
    )


def _sales_timeseries(days=14):
    today = localdate()
    since = today - timedelta(days=days)
    qs = (
        SalesHeader.objects
        .filter(created_at__date__gte=since)
        .values("created_at__date")
        .annotate(revenue=Coalesce(Sum("total"), dec0_expr()))
        .order_by("created_at__date")
    )
    labels = [str(r["created_at__date"]) for r in qs]
    values = [float(r["revenue"]) for r in qs]
    return labels, values

#load suppliers on product edit

@login_required
def product_edit(request, pk):
    product = Product.objects.get(pk=pk)
    suppliers = Supplier.objects.filter(active=True).order_by("name")

    return render(request, "accounts/product_edit.html", {
        "product": product,
        "suppliers": suppliers,
        "mode": "edit",
        "api_url": f"/api/products/{pk}/",
    })


# ============================================================
#  DASHBOARD VIEW (now role-safe and context-safe)
# ============================================================

@login_required
def dashboard(request):
    today = localdate()
    last_14 = today - timedelta(days=14)
    last_30 = today - timedelta(days=30)

    # Always-available metrics
    total_sales = _total_sales_amount(days=30)
    stock_value = _stock_value_sum()

    # --------- ROLE: resolve safely and ALWAYS build context ---------
    role = get_user_role(request.user)

    low_stock_count = (
        StockLedger.objects
        .values("product_id", "branch_id")
        .annotate(on_hand=Coalesce(Sum("qty_change"), dec0_expr()))
        .filter(on_hand__lte=5)
        .count()
    )

    low_stock_items = list(
        StockLedger.objects
        .values(
            "product__sku",
            "product__name",
            "branch__name",
            "product_id",
            "branch_id"
        )
        .annotate(on_hand=Coalesce(Sum("qty_change"), dec0_expr()))
        .filter(on_hand__lte=5)
        .order_by("on_hand")
    )

    chart_labels, chart_values = _sales_timeseries(days=14)

    top5 = list(
        SalesLine.objects
        .filter(header__created_at__date__gte=last_30)
        .values("product_id", "product__sku", "product__name")
        .annotate(units=Coalesce(Sum("qty"), dec0_expr()))
        .order_by("-units")[:5]
    )

    # --------- Init fallback values ---------
    fc_labels, fc_actual, fc_pred = [], [], []
    pf_labels, pf_values = [], []
    leaderboard = []
    cashiers = []
    sparkline_series = []
    risk_scores = []
    avg_risk = 0
    max_risk = 0
    branch_comp = []
    pve_labels, pve_revenue, pve_expense = [], [], []
    notifications = []
    heatmap_data = []
    gauge_label, gauge_cover, gauge_target = None, None, 14
    gm = {"gm_pct": 0, "revenue": 0, "cogs": 0, "profit": 0}
    inv = {"health_score": 0, "low_stock": 0, "stockouts": 0, "dead_stock": 0}
    trend_labels, trend_rev, trend_profit = [], [], []
    fc7_labels, fc7_series = [], []
    pairs = []
    restock_list = []

    # --------- Try to compute widgets ---------
    try:
        # Forecasts & metrics
        fc_labels, fc_actual, fc_pred = forecast_vs_actual(days=14)
        pf_labels, pf_values = profit_sparkline(days=14)
        leaderboard = branch_leaderboard(limit=5)
        cashiers = cashier_leaderboard(limit=5)
        gm = gross_margin(30)
        inv = inventory_health()
        trend_labels, trend_rev, trend_profit = trend_30_days(30)
        fc7_labels, fc7_series = forecast_7_day()
        pairs = frequently_bought_together(30)

        # --------- RESTOCK (AI Reorder Recommendations) ---------
        restock_list = branch_restock_suggestions()[:20]
        # Add restock to context later
        # Compute gauge from restock_list
        if restock_list:
            first = restock_list[0]
            gauge_label = f"{first['sku']} – {first['name']}"

            # Use SAME cover_days as the table
            gauge_cover = (
                float(first["cover_days"])
                if first["cover_days"] is not None
                else None
            )
        else:
            gauge_label = "No data"
            gauge_cover = None

    except Exception as e:
        print("Dashboard widget error:", e)
        traceback.print_exc()

    # --------- Top 5 sparklines ---------
    try:
        for p in top5:
            label = f"{p['product__sku']} – {p['product__name']}"
            if Forecast:
                fc = (
                    Forecast.objects
                    .filter(product_id=p["product_id"], date__gte=today)
                    .order_by("date").values("date", "yhat")[:14]
                )
                fc = list(fc)
                if fc:
                    sparkline_series.append({
                        "label": label,
                        "labels": [str(r["date"]) for r in fc],
                        "values": [float(r["yhat"]) for r in fc],
                    })
                    continue

            hist = (
                SalesLine.objects
                .filter(product_id=p["product_id"], header__created_at__date__gte=last_14)
                .values("header__created_at__date")
                .annotate(units=Coalesce(Sum("qty"), dec0_expr()))
                .order_by("header__created_at__date")
            )
            sparkline_series.append({
                "label": label,
                "labels": [str(r["header__created_at__date"]) for r in hist],
                "values": [float(r["units"]) for r in hist],
            })
    except Exception as e:
        print("Sparkline error:", e)
        traceback.print_exc()

    # --------- Branch risk scoring ---------
    try:
        for b in Branch.objects.only("id", "name"):
            low_sku = (
                StockLedger.objects
                .filter(branch_id=b.id)
                .values("product_id")
                .annotate(on_hand=Coalesce(Sum("qty_change"), dec0_expr()))
                .filter(on_hand__lte=5)
                .count()
            )
            total_sku = (
                StockLedger.objects
                .filter(branch_id=b.id)
                .values("product_id")
                .distinct()
                .count()
            ) or 1

            low_ratio = low_sku / total_sku

            days_with_sales = (
                SalesLine.objects
                .filter(header__branch_id=b.id, header__created_at__date__gte=last_14)
                .values("header__created_at__date")
                .annotate(u=Coalesce(Sum("qty"), dec0_expr()))
                .count()
            )
            vol = max(0, 14 - days_with_sales) / 14
            score = min(100, int((0.7 * low_ratio + 0.3 * vol) * 100))

            risk_scores.append({"branch": b.name, "score": score})

        if risk_scores:
            avg_risk = int(sum(r["score"] for r in risk_scores) / len(risk_scores))
            max_risk = max((r["score"] for r in risk_scores), default=0)
    except Exception as e:
        print("Risk score error:", e)
        traceback.print_exc()

    # --------- Branch comparison last 30 days ---------
    try:
        branch_comp = list(
            SalesHeader.objects
            .filter(created_at__date__gte=last_30)
            .values("branch__name")
            .annotate(revenue=Coalesce(Sum("total"), dec0_expr()))
            .order_by("branch__name")
        )
    except Exception as e:
        print("Branch comparison error:", e)
        traceback.print_exc()

    # --------- Revenue vs Expense ---------
    try:
        rev_days = (
            SalesHeader.objects
            .filter(created_at__date__gte=last_14)
            .values("created_at__date")
            .annotate(revenue=Coalesce(Sum("total"), dec0_expr()))
            .order_by("created_at__date")
        )
        exp_map = {}
        if Expense:
            exp_days = (
                Expense.objects
                .filter(created_at__date__gte=last_14)
                .values("created_at__date")
                .annotate(expense=Coalesce(Sum("amount"), dec0_expr()))
                .order_by("created_at__date")
            )
            exp_map = {str(r["created_at__date"]): float(r["expense"]) for r in exp_days}

        pve_labels = [str(r["created_at__date"]) for r in rev_days]
        pve_revenue = [float(r["revenue"]) for r in rev_days]
        pve_expense = [exp_map.get(lbl, 0.0) for lbl in pve_labels]
    except Exception as e:
        print("Revenue vs Expense error:", e)
        traceback.print_exc()

    # --------- Notifications ---------
    try:
        if low_stock_items:
            level = (
                "danger" if len(low_stock_items) > 20
                else "warning" if len(low_stock_items) > 10
                else "success"
            )
            notifications.append({
                "level": level,
                "text": f"{len(low_stock_items)} products are below the low-stock threshold."
            })
            for item in low_stock_items[:20]:
                notifications.append({
                    "level": "danger",
                    "text": (
                        f"{item['product__sku']} – {item['product__name']} "
                        f"({item['branch__name']}) is low on stock: "
                        f"{int(item['on_hand'])} units"
                    )
                })
    except Exception:
        pass

    # --------- Heatmap ---------
    try:
        heatmap_raw = (
            SalesHeader.objects
            .extra(select={
                "weekday": "EXTRACT(DOW FROM created_at)",
                "hour": "EXTRACT(HOUR FROM created_at)"
            })
            .values("weekday", "hour")
            .annotate(total=Coalesce(Sum("total"), dec0_expr()))
        )
        heatmap_data = [
            {"x": int(i["hour"]), "y": int(i["weekday"]), "v": float(i["total"])}
            for i in heatmap_raw if i["hour"] is not None and i["weekday"] is not None
        ]
    except Exception as e:
        print("Heatmap error:", e)
        traceback.print_exc()

    # --------- Build final context ---------
    context = {
        "total_sales": total_sales,
        "stock_value": stock_value,
        "low_stock_count": low_stock_count,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "top5": top5,
        "sparkline_series": sparkline_series,
        "risk_scores": risk_scores,
        "avg_risk": avg_risk,
        "max_risk": max_risk,
        "branch_comp": branch_comp,
        "pve_labels": pve_labels,
        "pve_revenue": pve_revenue,
        "pve_expense": pve_expense,
        "notifications": notifications,
        "heatmap_data": heatmap_data,
        "leaderboard": leaderboard,
        "cashiers": cashiers,
        "role": role,
        "gm": gm,
        "inv": inv,
        "tr30_labels": trend_labels,
        "tr30_revenue": trend_rev,
        "tr30_profit": trend_profit,
        "fc7_labels": fc7_labels,
        "fc7_series": fc7_series,
        "pairs": pairs,
        "low_stock_items": low_stock_items,
        
        "total_sales": total_sales,
        "top5": top5,
        "low_stock_count": low_stock_count,
        "avg_risk": avg_risk,
        "pf_values": pf_values,
        "pf_labels":pf_labels,
        
        "fc_labels": fc_labels,
        "fc_actual": fc_actual,
        "fc_pred": fc_pred,


    }

 

    # Add restock and gauge computed earlier
    context["restock"] = restock_list
    context["gauge_label"] = gauge_label
    context["gauge_cover"] = gauge_cover
    context["gauge_target"] = 14

    # Transfers
    context["transfers"] = build_transfer_matrix()[:30]
    context["insights"] = ai_insights(context)
    context.update(_dashboard_report_data(request))

    return render(request, "accounts/dashboard.html", context)


@login_required
def inventory_profit_reports(request):
    return render(
        request,
        "accounts/inventory_profit_reports.html",
        _dashboard_report_data(request),
    )


# ============================================================
#  OTHER VIEWS (unchanged but cleaned)
# ============================================================
#Reversals
@login_required
def sales(request):
    # KPIs
    last_30 = localdate() - timedelta(days=30)
   

    top_products = (
        SalesLine.objects
        .filter(
            header__created_at__date__gte=last_30,
            header__status="POSTED"
        )
        .values(
            "product__sku",
            "product__name"
        )
        .annotate(
            units=Coalesce(Sum("qty"), dec0_expr()),
            revenue=Coalesce(Sum("line_total"), dec0_expr()),
        )
        .order_by("-units")[:10]
    )

  

    revenue = (
        SalesHeader.objects
        .filter(created_at__date__gte=last_30)
        .aggregate(val=Coalesce(Sum("total"), dec0_expr()))["val"]
    )

    orders = (
        SalesHeader.objects
        .filter(created_at__date__gte=last_30)
        .count()
    )

    aov = (revenue / orders) if orders else DEC0

    # Insurance dropdown
    insurances = (
        Insurance.objects
        .filter(is_active=True)
        .order_by("name")
    )

    # Reversals
    reversals = (
        SaleReversal.objects
        .select_related("header", "reversed_by")
    )

    f = request.GET.get("from")
    t = request.GET.get("to")
    q = request.GET.get("q")

    if f:
        reversals = reversals.filter(
            created_at__date__gte=parse_date(f)
        )

    if t:
        reversals = reversals.filter(
            created_at__date__lte=parse_date(t)
        )

    if q:
        reversals = reversals.filter(
            Q(header__sale_id__icontains=q) |
            Q(reversed_by__username__icontains=q) |
            Q(reason__icontains=q)
        )

    reversals = reversals.order_by("-created_at")

    return render(
        request,
        "accounts/sales.html",
        {
            "revenue": revenue,
            "orders": orders,
            "aov": aov,

            "insurances": insurances,

            "top_products": top_products,

            "reversals": reversals,

            "from": f or "",
            "to": t or "",
            "q": q or "",
        }
    )



@login_required
def generate_missing_barcodes(request):

    products = Product.objects.filter(
        barcode__isnull=True
    ) | Product.objects.filter(
        barcode=""
    )

    count = 0

    for product in products:

        product.barcode = str(
            random.randint(
                100000000000,
                999999999999
            )
        )

        product.save(update_fields=["barcode"])

        count += 1

    messages.success(
        request,
        f"{count} barcodes generated."
    )

    return redirect("accounts:products")


@login_required
def products(request):
    total_products = Product.objects.count()

    active_products = Product.objects.filter(
        active=True
    ).count()

    products = (
        Product.objects
        .select_related("supplier")
        .order_by("name")
    )

    try:
        low_stock = (
            StockLedger.objects
            .values("product__sku", "product__name")
            .annotate(
                on_hand=Coalesce(
                    Sum("qty_change"),
                    Value(0,output_field=DecimalField(max_digits=14,decimal_places=4))
                )
            )
            .filter(on_hand__lte=5)
            .order_by("on_hand")[:20]
        )
    except Exception:
        low_stock = []

    return render(
        request,
        "accounts/products.html",
        {
            "products": products,
            "total_products": total_products,
            "active_products": active_products,
            "low_stock": low_stock,
        }
    )


@login_required
def suppliers_dashboard(request):
    total_suppliers = Supplier.objects.count()
    active_suppliers = Supplier.objects.filter(active=True).count()

    return render(request, "accounts/suppliers_manage_list.html", {
        "total_suppliers": total_suppliers,
        "active_suppliers": active_suppliers,
    })



# ============================================================
#  INVENTORY
# ============================================================

@login_required
def inventory(request):
    branch = _active_branch(request)

    # Branch summary
    try:
        cost_field = _detect_batch_cost_field()

        qs_branch = (
            StockLedger.objects
            .values("branch__name")
            .annotate(
                on_hand=Coalesce(Cast(Sum("qty_change"), DEC_FIELD), dec0_expr())
            )
        )

        qty_dec = Cast(F("qty_change"), output_field=DEC_FIELD)

        if cost_field:
            line_value = ExpressionWrapper(
                qty_dec * Cast(Coalesce(F(cost_field), dec0_expr()), DEC_FIELD),
                output_field=DEC_FIELD,
            )
            qs_branch = qs_branch.annotate(value=Coalesce(Sum(line_value), dec0_expr()))
        else:
            qs_branch = qs_branch.annotate(value=dec0_expr())

        by_branch = qs_branch.order_by("-value")

    except Exception:
        by_branch = []

    # Product-level
    
    qs_product = (
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
        qs_product = qs_product.filter(branch_id=branch.id)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs_product = qs_product.filter(
            Q(product__name__icontains=q) |
            Q(product__sku__icontains=q) |
            Q(product__supplier__name__icontains=q)
        )

    today = timezone.localdate()
    batch_totals = (
        StockBatch.objects.filter(qty_on_hand__gt=0)
        .values("product_id", "branch_id")
        .annotate(
            expired_qty=Coalesce(
                Sum(
                    Case(
                        When(expiry_date__lte=today, then=F("qty_on_hand")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=14, decimal_places=4),
                    )
                ),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=4)),
            ),
            usable_qty=Coalesce(
                Sum(
                    Case(
                        When(Q(expiry_date__isnull=True) | Q(expiry_date__gt=today), then=F("qty_on_hand")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=14, decimal_places=4),
                    )
                ),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=4)),
            ),
        )
    )
    batch_total_map = {
        (row["product_id"], row["branch_id"]): row
        for row in batch_totals
    }
    products = list(qs_product)
    for product in products:
        totals = batch_total_map.get((product["product__id"], product["branch_id"]), {})
        product["expired_qty"] = totals.get("expired_qty", Decimal("0"))
        product["usable_qty"] = totals.get("usable_qty", Decimal("0"))

    return render(request, "accounts/inventory.html", {
        "by_branch": by_branch,
        "products": products,
        "q": q,
    })


# ============================================================
#  REPORTS
# ============================================================

def _export_ledger_csv(queryset):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="stock_ledger_{localdate()}.csv"'
    w = csv.writer(resp)
    w.writerow(["Date", "Time", "Branch", "SKU", "Product", "Batch", "Expiry", "Qty Change", "Reason", "Reference"])

    for x in queryset.select_related("product", "branch", "batch"):
        dt = localtime(x.created_at)
        w.writerow([
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%H:%M:%S"),
            x.branch.name,
            x.product.sku,
            x.product.name,
            x.batch.batch_no if x.batch_id else "",
            x.batch.expiry_date.isoformat() if (x.batch_id and x.batch.expiry_date) else "",
            float(x.qty_change),
            x.reason,
            x.reference or "",
        ])

    return resp


def _export_ledger_excel(queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Ledger"

    ws.append(["Date", "Time", "Branch", "SKU", "Product", "Batch", "Expiry", "Qty Change", "Reason", "Reference"])

    for x in queryset.select_related("product", "branch", "batch"):
        dt = localtime(x.created_at)
        ws.append([
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%H:%M:%S"),
            x.branch.name,
            x.product.sku,
            x.product.name,
            x.batch.batch_no if x.batch_id else "",
            x.batch.expiry_date.isoformat() if (x.batch_id and x.batch.expiry_date) else "",
            float(x.qty_change),
            x.reason,
            x.reference or "",
        ])

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="stock_ledger_{localdate()}.xlsx"'
    wb.save(resp)
    return resp


@login_required
def reports(request):
    dfrom, dto = _parse_range(request, default_days=30)
    branch = _active_branch(request)

    qs = (
        StockLedger.objects
        .filter(created_at__date__range=[dfrom, dto])
        .select_related("product", "branch", "batch")
        .order_by("-created_at")
    )

    if branch:
        qs = qs.filter(branch=branch)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(product__sku__icontains=q) |
            Q(product__name__icontains=q) |
            Q(reference__icontains=q)
        )

    export_format = (request.GET.get("export") or "").lower()

    if export_format == "csv":
        return _export_ledger_csv(qs)
    elif export_format == "excel":
        return _export_ledger_excel(qs)

    daily = (
        StockLedger.objects
        .filter(created_at__date__range=[dfrom, dto])
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(
            qty_in_sum=Sum("qty_change", filter=Q(reason="IN")),
            qty_out_sum=Sum("qty_change", filter=Q(reason="OUT")),
            net_sum=Sum("qty_change"),
        )
        .order_by("date")
    )

    if branch:
        daily = daily.filter(branch=branch)

    row_count = qs.count()
    branch_name = branch.name if branch else "All branches"

    return render(request, "accounts/reports.html", {
        "queryset": qs[:200],
        "daily": daily,
        "from": dfrom.isoformat(),
        "to": dto.isoformat(),
        "q": q,
        "row_count": row_count,
        "branch_name": branch_name,
    })