# accounts/views/report_views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Avg, Min, Max, Count, Q

from accounts.models.sales import SalesHeader, SalesLine
from accounts.models.expense import Expense

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from accounts.services.analytics import (
    sales_analytics, inventory_analytics, stock_velocity,
    data_quality_report, supplier_price_intelligence,
    abc_product_analysis, forecast_accuracy,
)
from accounts.models.org import Branch
from accounts.models import Product
from django.contrib.auth.models import User
from datetime import date
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from accounts.models.stock import StockBatch, StockLedger
from accounts.models.purchase import PurchaseHeader, PurchaseLine, Supplier
from accounts.models.procurement import SupplierQuotationLine
from accounts.models.procurement_execution import GoodsReceiptLine
from ai.models import Forecast


@login_required
def stock_aging(request):
    branch_id = request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None)
    batches = StockBatch.objects.filter(qty_on_hand__gt=0).select_related("product", "branch")
    if branch_id:
        batches = batches.filter(branch_id=branch_id)
    rows = []
    today = timezone.localdate()
    for batch in batches:
        first_in = StockLedger.objects.filter(
            product=batch.product,
            branch=batch.branch,
            batch=batch,
            qty_change__gt=0,
        ).aggregate(first=Min("created_at"))["first"]
        days = (today - (first_in.date() if first_in else today)).days
        band = "0-30 days" if days <= 30 else "31-90 days" if days <= 90 else "91-180 days" if days <= 180 else "180+ days"
        rows.append({"product": batch.product, "branch": batch.branch, "qty": batch.qty_on_hand, "days": days, "band": band})
    rows.sort(key=lambda row: row["days"], reverse=True)
    bands = [
        {"label": "0-30 days", "target": "age30", "rows": [row for row in rows if row["band"] == "0-30 days"]},
        {"label": "31-60 days", "target": "age60", "rows": [row for row in rows if row["band"] == "31-60 days"]},
        {"label": "61-90 days", "target": "age90", "rows": [row for row in rows if row["band"] == "61-90 days"]},
        {"label": "Above 90 days", "target": "ageOlder", "rows": [row for row in rows if row["band"] in {"91-180 days", "180+ days"}]},
    ]
    return render(
        request,
        "accounts/reports/stock_aging.html",
        {"rows": rows, "bands": bands, "branches": Branch.objects.filter(active=True).order_by("name")},
    )


@login_required
def procurement_savings(request):
    rows = []
    for product_id in SupplierQuotationLine.objects.filter(
        unit_price__gt=0,
        quotation__status__in=["AWARDED", "ORDERED"],
    ).values_list("product_id", flat=True).distinct():
        quotes = SupplierQuotationLine.objects.filter(product_id=product_id, unit_price__gt=0)
        awarded = quotes.filter(awarded=True).aggregate(cost=Avg("unit_price"))["cost"]
        highest = quotes.aggregate(cost=Max("unit_price"))["cost"]
        if awarded is not None and highest is not None:
            rows.append({"product": Product.objects.get(pk=product_id), "saving": highest - awarded, "market": highest, "awarded": awarded})
    return render(
        request,
        "accounts/reports/procurement_savings.html",
        {"rows": rows, "savings": sum((row["saving"] for row in rows), Decimal("0"))},
    )


@login_required
def supplier_performance(request):
    suppliers = []
    for supplier in Supplier.objects.filter(active=True).order_by("name"):
        orders = PurchaseHeader.objects.filter(supplier=supplier)
        receipt_lines = GoodsReceiptLine.objects.filter(po_line__header__supplier=supplier)
        ordered = PurchaseLine.objects.filter(header__supplier=supplier).aggregate(total=Sum("qty"))["total"] or Decimal("0")
        received = receipt_lines.aggregate(total=Sum("received_qty"))["total"] or Decimal("0")
        lead_times = []
        for receipt in receipt_lines.select_related("receipt__po"):
            lead_times.append((receipt.receipt.received_at.date() - receipt.receipt.po.purchase_date).days)
        suppliers.append({
            "name": supplier.name,
            "orders": orders.count(),
            "lead_time": f"{sum(lead_times) / len(lead_times):.1f} days" if lead_times else "-",
            "fill_rate": round(float(received / ordered * 100), 1) if ordered else 0,
        })
    return render(
        request,
        "accounts/reports/supplier_performance.html",
        {"suppliers": suppliers},
    )


@login_required
def margin_analysis(request):
    branch_id = request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None)
    lines = SalesLine.objects.all()
    if branch_id:
        lines = lines.filter(header__branch_id=branch_id)
    rows = []
    for row in lines.values("product_id", "product__name").annotate(
        sales=Sum("line_total"),
        cost=Sum(ExpressionWrapper(F("qty") * F("line_cost"), output_field=DecimalField(max_digits=18, decimal_places=4))),
    ).order_by("product__name"):
        profit = (row["sales"] or 0) - (row["cost"] or 0)
        row["margin"] = (profit / row["sales"] * 100) if row["sales"] else 0
        row["product"] = row.pop("product__name")
        rows.append(row)
    return render(
        request,
        "accounts/reports/margin_analysis.html",
        {"rows": rows, "branches": Branch.objects.filter(active=True).order_by("name")},
    )


@login_required
def data_quality(request):
    findings = data_quality_report()
    return render(request, "accounts/reports/data_quality.html", {
        "findings": findings,
        "high_count": sum(1 for finding in findings if finding["severity"] == "HIGH"),
        "medium_count": sum(1 for finding in findings if finding["severity"] == "MEDIUM"),
    })


@login_required
def supplier_price_intelligence_report(request):
    return render(request, "accounts/reports/supplier_price_intelligence.html", {
        "rows": supplier_price_intelligence(request.GET.get("product")),
        "products": Product.objects.filter(active=True).order_by("name"),
    })


@login_required
def abc_analysis_report(request):
    return render(request, "accounts/reports/abc_analysis.html", {
        "rows": abc_product_analysis(
            request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None),
            request.GET.get("start"),
            request.GET.get("end"),
        ),
    })


@login_required
def forecast_accuracy_report(request):
    return render(request, "accounts/reports/forecast_accuracy.html", {
        "rows": forecast_accuracy(
            request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None),
            int(request.GET.get("days", 30)),
        ),
    })


def _forecast_rows(request):
    branch_id = request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None)
    horizon = timezone.localdate() + timedelta(days=int(request.GET.get("days", 30)))
    forecasts = Forecast.objects.filter(date__gte=timezone.localdate(), date__lte=horizon).select_related("product", "branch")
    if branch_id:
        forecasts = forecasts.filter(branch_id=branch_id)
    return forecasts.values("product_id", "product__sku", "product__name", "branch__name").annotate(
        forecast_qty=Sum("yhat"),
        forecast_low=Sum("yhat_lower"),
        forecast_high=Sum("yhat_upper"),
    ).order_by("product__name")


@login_required
def sales_forecasting(request):
    return render(request, "accounts/reports/sales_forecasting.html", {
        "rows": _forecast_rows(request),
        "branches": Branch.objects.filter(active=True).order_by("name"),
        "days": request.GET.get("days", 30),
    })


@login_required
def procurement_plan(request):
    forecasts = list(_forecast_rows(request))
    branch_id = request.GET.get("branch") or getattr(getattr(request, "active_branch", None), "id", None)
    rows = []
    for row in forecasts:
        stock = StockBatch.objects.filter(product_id=row["product_id"], **({"branch_id": branch_id} if branch_id else {})).aggregate(total=Sum("qty_on_hand"))["total"] or Decimal("0")
        product = Product.objects.get(pk=row["product_id"])
        suggested = max(Decimal("0"), Decimal(str(row["forecast_qty"] or 0)) - stock, Decimal(product.reorder_qty or 0))
        rows.append({**row, "on_hand": stock, "reorder_level": product.reorder_level, "suggested_qty": suggested})
    return render(request, "accounts/reports/procurement_plan.html", {
        "rows": rows,
        "branches": Branch.objects.filter(active=True).order_by("name"),
        "days": request.GET.get("days", 30),
    })


def _analytics_filters(request):
    branch_id = request.GET.get("branch") or getattr(request, "active_branch", None)
    branch_id = getattr(branch_id, "id", branch_id)
    start = request.GET.get("start") or None
    end = request.GET.get("end") or None
    limit = request.GET.get("limit", "10")
    user_id = request.GET.get("user") or None
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10
    return branch_id, start, end, limit, user_id


@login_required
def analytics_dashboard(request):
    branch_id, start, end, limit, user_id = _analytics_filters(request)
    return render(request, "accounts/reports/analytics_dashboard.html", {
        "branches": Branch.objects.filter(active=True).order_by("name"),
        "users": User.objects.filter(is_active=True).order_by("username"),
        "selected_branch": str(branch_id or ""),
        "selected_user": str(user_id or ""),
        "start": start or (timezone.localdate() - timedelta(days=364)).isoformat(),
        "end": end or "",
        "limit": limit,
    })


@login_required
def analytics_api(request):
    branch_id, start, end, limit, user_id = _analytics_filters(request)
    sales = sales_analytics(branch_id, start, end, limit, user_id)
    velocity = stock_velocity(branch_id, start, end)
    inventory = inventory_analytics(branch_id)
    return JsonResponse({
        "sales": sales,
        "velocity": velocity,
        "inventory": inventory,
    }, encoder=DjangoJSONEncoder)
    
class ProfitLossView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.active_branch:
            return Response({"detail": "Active branch not set"}, status=400)

        start = request.query_params.get("start")
        end = request.query_params.get("end")

        hdr_qs = SalesHeader.objects.filter(branch=request.active_branch)

        if start:
            hdr_qs = hdr_qs.filter(created_at__date__gte=start)
        if end:
            hdr_qs = hdr_qs.filter(created_at__date__lte=end)

        # Revenue
        line_qs = SalesLine.objects.filter(header__in=hdr_qs)
        revenue = line_qs.aggregate(s=Sum("line_total"))["s"] or 0

        # COGS
        cost_expr = ExpressionWrapper(F("qty") * F("line_cost"), output_field=DecimalField())
        cogs = line_qs.aggregate(s=Sum(cost_expr))["s"] or 0

        # Expenses
        exp_qs = Expense.objects.filter(branch=request.active_branch)
        if start:
            exp_qs = exp_qs.filter(date__gte=start)
        if end:
            exp_qs = exp_qs.filter(date__lte=end)
        expenses = exp_qs.aggregate(s=Sum("amount"))["s"] or 0

        gp = revenue - cogs
        np = gp - expenses

        return Response({
            "branch": request.active_branch.code,
            "period": {"start": start, "end": end},
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gp,
            "expenses": expenses,
            "net_profit": np,
        })