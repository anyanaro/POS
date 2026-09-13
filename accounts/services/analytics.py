from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value, OuterRef, Subquery, Avg, Max, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.models.product import Product
from accounts.models.sales import SalesHeader, SalesLine
from accounts.models.stock import StockBatch
from accounts.models.procurement_execution import GoodsReceiptLine
from accounts.models.purchase import PurchaseLine
from accounts.models.procurement import ProductCostHistory
from ai.models import Forecast


def _date_range(start=None, end=None, days=30):
    today = timezone.localdate()
    end_date = parse_date(end) if isinstance(end, str) else end
    start_date = parse_date(start) if isinstance(start, str) else start
    end_date = end_date or today
    start_date = start_date or (end_date - timedelta(days=days - 1))
    return start_date, end_date


def sales_analytics(branch_id=None, start=None, end=None, limit=10, user_id=None):
    start_date, end_date = _date_range(start, end, days=365)
    lines = SalesLine.objects.filter(
        header__created_at__date__range=(start_date, end_date),
    )
    if branch_id:
        lines = lines.filter(header__branch_id=branch_id)
    if user_id:
        lines = lines.filter(header__cashier_id=user_id)

    purchase_cost = PurchaseLine.objects.filter(
        batch_id=OuterRef("batch_id"),
        product_id=OuterRef("product_id"),
        buying_cost__isnull=False,
    ).order_by("id").values("buying_cost")[:1]
    lines = lines.annotate(
        purchase_buying_cost=Coalesce(
            Subquery(purchase_cost, output_field=DecimalField(max_digits=12, decimal_places=4)),
            F("line_cost"),
        )
    )
    gross_profit_expression = ExpressionWrapper(
        (F("unit_price") - F("purchase_buying_cost")) * F("qty"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    rows = list(
        lines.values(
            "product_id",
            "product__sku",
            "product__name",
        ).annotate(
            units=Coalesce(Sum("qty"), Value(Decimal("0"))),
            revenue=Coalesce(Sum("line_total"), Value(Decimal("0"))),
            cogs=Coalesce(Sum(ExpressionWrapper(
                F("qty") * F("purchase_buying_cost"),
                output_field=DecimalField(max_digits=18, decimal_places=4),
            )), Value(Decimal("0"))),
            gross_profit=Coalesce(Sum(gross_profit_expression), Value(Decimal("0"))),
        ).order_by("-revenue")
    )
    for row in rows:
        row["gross_profit"] = row["gross_profit"]
        row["margin_pct"] = (
            row["gross_profit"] / row["revenue"] * Decimal("100")
            if row["revenue"] else Decimal("0")
        )
    return {
        "period": {"start": start_date, "end": end_date},
        "totals": {
            "units": sum((row["units"] for row in rows), Decimal("0")),
            "revenue": sum((row["revenue"] for row in rows), Decimal("0")),
            "cogs": sum((row["cogs"] for row in rows), Decimal("0")),
            "gross_profit": sum((row["gross_profit"] for row in rows), Decimal("0")),
        },
        "products": rows[:max(1, min(int(limit), 50))],
        "branches": sales_by_branch(branch_id, start_date, end_date, user_id),
        "users": sales_by_user(branch_id, start_date, end_date, user_id),
    }


def sales_by_branch(branch_id=None, start=None, end=None, user_id=None):
    lines = SalesLine.objects.filter(
        header__created_at__date__range=(start, end),
    )
    if branch_id:
        lines = lines.filter(header__branch_id=branch_id)
    if user_id:
        lines = lines.filter(header__cashier_id=user_id)
    purchase_cost = PurchaseLine.objects.filter(
        batch_id=OuterRef("batch_id"),
        product_id=OuterRef("product_id"),
        buying_cost__isnull=False,
    ).order_by("id").values("buying_cost")[:1]
    lines = lines.annotate(
        purchase_buying_cost=Coalesce(
            Subquery(purchase_cost, output_field=DecimalField(max_digits=12, decimal_places=4)),
            F("line_cost"),
        )
    )
    gross_profit_expression = ExpressionWrapper(
        (F("unit_price") - F("purchase_buying_cost")) * F("qty"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    rows = list(lines.values(
        "header__branch_id",
        "header__branch__name",
    ).annotate(
        units=Coalesce(Sum("qty"), Value(Decimal("0"))),
        revenue=Coalesce(Sum("line_total"), Value(Decimal("0"))),
        cogs=Coalesce(Sum(ExpressionWrapper(
            F("qty") * F("purchase_buying_cost"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )), Value(Decimal("0"))),
        gross_profit=Coalesce(Sum(gross_profit_expression), Value(Decimal("0"))),
    ).order_by("-revenue"))
    for row in rows:
        row["margin_pct"] = (
            row["gross_profit"] / row["revenue"] * Decimal("100")
            if row["revenue"] else Decimal("0")
        )
    return rows


def sales_by_user(branch_id=None, start=None, end=None, user_id=None):
    lines = SalesLine.objects.filter(
        header__created_at__date__range=(start, end),
    )
    if branch_id:
        lines = lines.filter(header__branch_id=branch_id)
    if user_id:
        lines = lines.filter(header__cashier_id=user_id)
    purchase_cost = PurchaseLine.objects.filter(
        batch_id=OuterRef("batch_id"),
        product_id=OuterRef("product_id"),
        buying_cost__isnull=False,
    ).order_by("id").values("buying_cost")[:1]
    lines = lines.annotate(
        purchase_buying_cost=Coalesce(
            Subquery(purchase_cost, output_field=DecimalField(max_digits=12, decimal_places=4)),
            F("line_cost"),
        )
    )
    gross_profit_expression = ExpressionWrapper(
        (F("unit_price") - F("purchase_buying_cost")) * F("qty"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    rows = list(lines.values(
        "header__cashier_id",
        "header__cashier__username",
        "header__branch_id",
        "header__branch__name",
    ).annotate(
        units=Coalesce(Sum("qty"), Value(Decimal("0"))),
        revenue=Coalesce(Sum("line_total"), Value(Decimal("0"))),
        cogs=Coalesce(Sum(ExpressionWrapper(
            F("qty") * F("purchase_buying_cost"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )), Value(Decimal("0"))),
        gross_profit=Coalesce(Sum(gross_profit_expression), Value(Decimal("0"))),
    ).order_by("-revenue"))
    for row in rows:
        row["gross_profit"] = row["gross_profit"]
        row["margin_pct"] = (
            row["gross_profit"] / row["revenue"] * Decimal("100")
            if row["revenue"] else Decimal("0")
        )
    return rows


def inventory_analytics(branch_id=None):
    batches = StockBatch.objects.select_related("product", "branch")
    if branch_id:
        batches = batches.filter(branch_id=branch_id)
    rows = list(
        batches.values(
            "product_id",
            "product__sku",
            "product__name",
            "product__unit_price",
            "product__reorder_level",
            "branch_id",
            "branch__name",
        ).annotate(
            on_hand=Coalesce(Sum("qty_on_hand"), Value(Decimal("0"))),
            cost_value=Coalesce(Sum(
                ExpressionWrapper(
                    F("qty_on_hand") * F("buying_cost"),
                    output_field=DecimalField(max_digits=20, decimal_places=4),
                )
            ), Value(Decimal("0"))),
            retail_value=Coalesce(Sum(
                ExpressionWrapper(
                    F("qty_on_hand") * F("product__unit_price"),
                    output_field=DecimalField(max_digits=20, decimal_places=4),
                )
            ), Value(Decimal("0"))),
        ).order_by("product__name", "branch__name")
    )
    for row in rows:
        row["reorder_due"] = row["on_hand"] <= (row["product__reorder_level"] or 0)
    return rows


def stock_velocity(branch_id=None, start=None, end=None):
    start_date, end_date = _date_range(start, end, days=90)
    lines = SalesLine.objects.filter(
        header__created_at__date__range=(start_date, end_date),
    )
    if branch_id:
        lines = lines.filter(header__branch_id=branch_id)
    sold = {
        row["product_id"]: row["units"]
        for row in lines.values("product_id").annotate(units=Coalesce(Sum("qty"), Value(Decimal("0"))))
    }
    stock = StockBatch.objects.filter(qty_on_hand__gt=0)
    if branch_id:
        stock = stock.filter(branch_id=branch_id)
    stock = stock.values("product_id").annotate(on_hand=Sum("qty_on_hand"))
    stock_by_product = {row["product_id"]: row["on_hand"] for row in stock}
    result = []
    today = timezone.localdate()
    for product in Product.objects.filter(active=True).order_by("name"):
        units = sold.get(product.id, Decimal("0"))
        on_hand = stock_by_product.get(product.id, Decimal("0"))
        daily_velocity = units / Decimal(max(1, (end_date - start_date).days + 1))
        days_on_hand = on_hand / daily_velocity if daily_velocity else None
        product_batches = StockBatch.objects.filter(
            product_id=product.id,
            qty_on_hand__gt=0,
            **({"branch_id": branch_id} if branch_id else {}),
        )
        first_grn = GoodsReceiptLine.objects.filter(
            product_id=product.id,
            batch_no__in=product_batches.values("batch_no"),
            **({"receipt__branch_id": branch_id} if branch_id else {}),
        ).order_by("receipt__received_at").values_list("receipt__received_at", flat=True).first()
        stock_age_days = (today - first_grn.date()).days if first_grn else None
        expiry_dates = list(product_batches.exclude(expiry_date__isnull=True).values_list("expiry_date", flat=True))
        days_to_expire = (
            sum((expiry - today).days for expiry in expiry_dates) / len(expiry_dates)
            if expiry_dates else None
        )
        if days_to_expire is not None and days_to_expire <= 0:
            classification = "EXPIRED"
        elif days_to_expire is not None and days_to_expire <= 30:
            classification = "EXPIRING"
        elif units <= 0:
            classification = "DEAD"
        elif units >= on_hand * Decimal("0.5") or daily_velocity >= Decimal("1"):
            classification = "FAST"
        else:
            classification = "SLOW"
        result.append({
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "units_sold": units,
            "on_hand": on_hand,
            "daily_velocity": daily_velocity,
            "days_on_hand": days_on_hand,
            "stock_age_days": stock_age_days,
            "days_to_expire": days_to_expire,
            "classification": classification,
        })
    return result


def data_quality_report():
    findings = []
    products = Product.objects.filter(active=True)
    for product in products:
        if not product.buying_cost or product.buying_cost <= 0:
            findings.append({
                "severity": "HIGH",
                "category": "PRODUCT COST",
                "product": product,
                "message": "Buying cost is zero or missing.",
            })
        if product.unit_price < product.buying_cost:
            findings.append({
                "severity": "HIGH",
                "category": "PRICING",
                "product": product,
                "message": "Selling price is below buying cost.",
            })
        if product.min_margin_pct > product.max_margin_pct:
            findings.append({
                "severity": "HIGH",
                "category": "PRICING",
                "product": product,
                "message": "Minimum margin exceeds maximum margin.",
            })

    batches = StockBatch.objects.filter(qty_on_hand__gt=0).select_related("product", "branch")
    for batch in batches:
        if not PurchaseLine.objects.filter(
            product=batch.product,
            batch=batch,
        ).exists():
            findings.append({
                "severity": "MEDIUM",
                "category": "STOCK PROVENANCE",
                "product": batch.product,
                "branch": batch.branch,
                "message": f"Batch {batch.batch_no} has no linked purchase line.",
            })

    return findings


def supplier_price_intelligence(product_id=None):
    history = ProductCostHistory.objects.select_related("product", "supplier")
    purchase_history = PurchaseLine.objects.filter(
        buying_cost__isnull=False,
        header__supplier__isnull=False,
    ).select_related("product", "header__supplier")
    if product_id:
        history = history.filter(product_id=product_id)
        purchase_history = purchase_history.filter(product_id=product_id)
    rows = list(purchase_history.values(
        "product_id", "product__sku", "product__name", "header__supplier_id", "header__supplier__name"
    ).annotate(
        average_cost=Avg("buying_cost"),
        last_cost=Max("buying_cost"),
        orders=Count("header_id", distinct=True),
        last_purchase=Max("header__purchase_date"),
    ).order_by("product__name", "average_cost"))
    for row in rows:
        market = purchase_history.filter(product_id=row["product_id"]).aggregate(avg=Avg("buying_cost"))["avg"]
        row["variance_pct"] = (
            (row["average_cost"] - market) / market * Decimal("100")
            if market else Decimal("0")
        )
    return rows


def abc_product_analysis(branch_id=None, start=None, end=None):
    sales = sales_analytics(branch_id, start, end, limit=50)["products"]
    total = sum((row["revenue"] for row in sales), Decimal("0"))
    cumulative = Decimal("0")
    for row in sales:
        cumulative += row["revenue"]
        share = cumulative / total * Decimal("100") if total else Decimal("0")
        row["abc_class"] = "A" if share <= 80 else "B" if share <= 95 else "C"
    return sales


def forecast_accuracy(branch_id=None, days=30):
    today = timezone.localdate()
    forecasts = Forecast.objects.filter(
        date__lt=today,
        date__gte=today - timedelta(days=days),
    )
    if branch_id:
        forecasts = forecasts.filter(branch_id=branch_id)
    rows = []
    for forecast in forecasts.select_related("product", "branch"):
        actual = SalesLine.objects.filter(
            product=forecast.product,
            header__branch=forecast.branch,
            header__created_at__date=forecast.date,
        ).aggregate(total=Sum("qty"))["total"] or Decimal("0")
        error = abs(Decimal(str(forecast.yhat)) - actual)
        rows.append({
            "date": forecast.date,
            "product": forecast.product,
            "branch": forecast.branch,
            "forecast": Decimal(str(forecast.yhat)),
            "actual": actual,
            "absolute_error": error,
        })
    return rows
