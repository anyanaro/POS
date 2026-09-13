# accounts/ai/engine.py
from datetime import date
from decimal import Decimal

from django.db.models import Sum, F, Value, DecimalField, IntegerField
from django.db.models.functions import Coalesce

from accounts.models import Product, SalesLine, SalesHeader, StockLedger, Branch

# ---------------- helpers: typed zeros ----------------
def dec0():
    return Value(Decimal("0.00"), output_field=DecimalField(max_digits=18, decimal_places=2))

def int0():
    return Value(0, output_field=IntegerField())


def _apply_date_filters(headers_qs, entities):
    since = entities.get("since")
    until = entities.get("until")
    if since:
        headers_qs = headers_qs.filter(created_at__date__gte=since)
    if until:
        headers_qs = headers_qs.filter(created_at__date__lte=until)
    return headers_qs

def _apply_line_date_filters(lines_qs, entities):
    since = entities.get("since")
    until = entities.get("until")
    if since:
        lines_qs = lines_qs.filter(header__created_at__date__gte=since)
    if until:
        lines_qs = lines_qs.filter(header__created_at__date__lte=until)
    return lines_qs

def _branch_filter_headers(qs, entities):
    b = entities.get("branch")
    if b:
        qs = qs.filter(branch__name__iexact=b)
    return qs

def _branch_filter_lines(qs, entities):
    b = entities.get("branch")
    if b:
        qs = qs.filter(header__branch__name__iexact=b)
    return qs

def _product_filter_lines(qs, entities):
    pid = entities.get("product_id")
    sku = entities.get("product_sku")
    name = entities.get("product_name")
    if pid:
        return qs.filter(product_id=pid)
    if sku:
        return qs.filter(product__sku__iexact=sku)
    if name:
        return qs.filter(product__name__iexact=name)
    return qs


def run_ai_query(intent, entities):
    """
    Maps detected AI intent -> Django ORM with optional filters:
      - branch: exact name (case-insensitive)
      - product_id / product_sku / product_name
      - since / until: ISO date strings (YYYY-MM-DD)
    """

    # --- Top selling products (optionally filtered by branch & dates) ---
    if intent == "top_products":
        qs = SalesLine.objects.all()
        qs = _product_filter_lines(qs, entities)
        qs = _branch_filter_lines(qs, entities)
        qs = _apply_line_date_filters(qs, entities)

        # Use Decimal output consistently to avoid mixed-type error
        qs = (qs
              .values("product__sku", "product__name")
              .annotate(units=Coalesce(Sum("qty"), dec0(), output_field=DecimalField(max_digits=18, decimal_places=2)))
              .order_by("-units")[:5])

        # If you prefer integer counts, you can instead do:
        # .annotate(units=Coalesce(Sum("qty"), int0(), output_field=IntegerField()))

        return {"type": "top_products", "rows": list(qs)}

    # --- Low stock items (optionally by branch) ---
    if intent == "low_stock":
        qs = StockLedger.objects.values("product__sku", "product__name", "product_id")
        branch = entities.get("branch")
        if branch:
            qs = qs.filter(branch__name__iexact=branch)

        # qty_change is usually IntegerField; keep it integer
        qs = (qs
              .annotate(on_hand=Coalesce(Sum("qty_change"), int0(), output_field=IntegerField()))
              .filter(on_hand__lte=5)
              .order_by("on_hand")[:50])

        return {"type": "low_stock", "rows": list(qs)}

    # --- Sales today (or within a given date range) ---
    if intent == "sales_today":
        headers = SalesHeader.objects.all()
        headers = _branch_filter_headers(headers, entities)

        # If since/until present, use them; else default = today
        if entities.get("since") or entities.get("until"):
            headers = _apply_date_filters(headers, entities)
        else:
            t = date.today()
            headers = headers.filter(created_at__date=t)

        total = headers.aggregate(t=Coalesce(Sum("total"), dec0(), output_field=DecimalField(max_digits=18, decimal_places=2)))["t"]
        return {"type": "sales_today", "total": float(total or 0)}

    # --- Branch performance ranking (optionally within date range) ---
    if intent == "branch_rank":
        headers = SalesHeader.objects.all()
        headers = _apply_date_filters(headers, entities)

        qs = (headers
              .values("branch__name")
              .annotate(revenue=Coalesce(Sum("total"), dec0(), output_field=DecimalField(max_digits=18, decimal_places=2)))
              .order_by("-revenue"))

        return {"type": "branch_rank", "rows": list(qs)}

    # --- Reorder suggestions (branch-aware) ---
    if intent == "reorder_recommendations":
        branch_name = entities.get("branch")
        branch_id = None
        if branch_name:
            branch_id = Branch.objects.filter(name__iexact=branch_name).values_list("id", flat=True).first()

        try:
            from accounts.services.reorder import reorder_recommendations as svc_reco
            recos = svc_reco(limit=10, target_days=14, safety=0.15, branch_id=branch_id)
        except Exception:
            recos = []

        payload = {"type": "reorder_recommendations", "rows": recos}
        if branch_name:
            payload["branch"] = branch_name
        return payload

    # Fallback
    return {
        "type": "unknown",
        "rows": [],
        "answer": "I understood the question but could not match it to a known query."
    }