from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction

from accounts.integrations.business_central import queue_sync, send_sync
from accounts.models.integration import BusinessCentralSync
from accounts.models.sales import SalesHeader
from accounts.models.purchase import PurchaseHeader
from accounts.models.procurement_execution import SupplierPayment


def _sale_payload(sale):
    return {
        "documentNo": str(sale.sale_id),
        "branch": sale.branch.code,
        "cashier": sale.cashier.username,
        "createdAt": sale.created_at,
        "total": sale.total,
        "lines": [
            {"sku": line.product.sku, "quantity": line.qty, "unitPrice": line.unit_price, "lineTotal": line.line_total}
            for line in sale.lines.select_related("product")
        ],
    }


def _purchase_payload(purchase):
    return {
        "documentNo": str(purchase.purchase_id),
        "branch": purchase.branch.code,
        "supplier": purchase.supplier.code if purchase.supplier else None,
        "purchaseDate": purchase.purchase_date,
        "total": purchase.total,
        "lines": [
            {"sku": line.product.sku, "quantity": line.qty, "unitCost": line.buying_cost, "lineTotal": line.line_total}
            for line in purchase.lines.select_related("product")
        ],
    }


@login_required
def queue_business_central_sync(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST required."}, status=405)
    counts = {"SALE": 0, "GRN": 0, "PAYMENT": 0}
    for sale in SalesHeader.objects.filter(posted_to_bc=False).select_related("branch", "cashier").prefetch_related("lines__product"):
        queue_sync("SALE", sale.sale_id, _sale_payload(sale))
        counts["SALE"] += 1
    for purchase in PurchaseHeader.objects.filter(status__in=["RECEIVED", "INVOICED"]).select_related("branch", "supplier").prefetch_related("lines__product"):
        queue_sync("GRN", purchase.purchase_id, _purchase_payload(purchase))
        counts["GRN"] += 1
    for payment in SupplierPayment.objects.select_related("invoice__supplier"):
        queue_sync("PAYMENT", payment.id, {
            "paymentId": payment.id,
            "supplier": payment.invoice.supplier.code,
            "amount": payment.amount,
            "paymentDate": payment.payment_date,
            "reference": payment.reference,
        })
        counts["PAYMENT"] += 1
    return JsonResponse({"queued": counts})


@login_required
def process_business_central_sync(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST required."}, status=405)
    records = BusinessCentralSync.objects.filter(status__in=["PENDING", "FAILED"], attempts__lt=3).order_by("created_at")[:100]
    results = {"sent": 0, "failed": 0}
    for record in records:
        result = send_sync(record)
        results["sent" if result.status == "SENT" else "failed"] += 1
    return JsonResponse(results)


@login_required
def business_central_dashboard(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "queue":
            result = queue_business_central_sync(request)
        elif action == "process":
            result = process_business_central_sync(request)
        else:
            result = JsonResponse({"detail": "Unknown action."}, status=400)
        if result.status_code == 200:
            import json
            data = json.loads(result.content)
            from django.contrib import messages
            messages.success(request, str(data))
        else:
            from django.contrib import messages
            messages.error(request, result.content.decode())
        from django.shortcuts import redirect
        return redirect("accounts:business-central")

    pending = BusinessCentralSync.objects.filter(status="PENDING").count()
    failed = BusinessCentralSync.objects.filter(status="FAILED").count()
    sent = BusinessCentralSync.objects.filter(status="SENT").count()
    return render(request, "accounts/integrations/business_central.html", {
        "pending": pending,
        "failed": failed,
        "sent": sent,
        "records": BusinessCentralSync.objects.order_by("-created_at")[:100],
    })
