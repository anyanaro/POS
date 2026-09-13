# accounts/services/reorder.py
from math import ceil
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Value, DecimalField, IntegerField, F
from django.db.models.functions import Coalesce
from accounts.models import Product, StockLedger, SalesLine

try:
    from ai.models import Forecast  # optional
except Exception:
    Forecast = None


def _dec0():
    return Value(Decimal("0.00"), output_field=DecimalField(max_digits=18, decimal_places=2))

def _int0():
    return Value(0, output_field=IntegerField())


def _on_hand(product_id, branch_id=None):
    qs = StockLedger.objects.filter(product_id=product_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return int(qs.aggregate(v=Coalesce(Sum("qty_change"), _int0()))["v"] or 0)


def _avg_daily_demand(product_id, branch_id=None, fallback_days=14, forecast_days=7) -> float:
    """
    Use Forecast if available; otherwise average last N days sold.
    """
    today = date.today()

    # Forecast path
    try:
        if Forecast:
            fq = Forecast.objects.filter(product_id=product_id, date__gte=today)
            if branch_id:
                fq = fq.filter(branch_id=branch_id)
            fq = fq.order_by("date").values("yhat")[:forecast_days]
            vals = [float(r["yhat"]) for r in fq]
            if vals:
                return sum(vals) / len(vals)
    except Exception:
        pass

    # Fallback: last N days units sold
    since = today - timedelta(days=fallback_days)
    sq = SalesLine.objects.filter(product_id=product_id, header__created_at__date__gte=since)
    if branch_id:
        sq = sq.filter(header__branch_id=branch_id)
    total_units = float(sq.aggregate(v=Coalesce(Sum("qty"), _dec0()))["v"] or 0.0)

    days = fallback_days or 1
    return total_units / days if days else 0.0


def reorder_recommendations(limit=10, target_days=14, safety=0.15, branch_id=None):
    """
    Branch-aware reorder recommendations.
    Returns: list of dicts [{sku, name, on_hand, daily_demand, cover, reco_qty}, ...]
    """
    recos = []
    # Sample only a subset for performance; tune as needed.
    for p in Product.objects.filter(active=True)[:200]:
        on_hand = _on_hand(p.id, branch_id=branch_id)
        daily = _avg_daily_demand(p.id, branch_id=branch_id)

        if daily <= 0:
            continue  # no demand

        cover = (on_hand / daily) if daily > 0 else None

        if cover is None or cover < target_days:
            target_qty = target_days * daily
            gap = max(0.0, target_qty - on_hand)
            reco = ceil(gap * (1.0 + safety))
            recos.append({
                "sku": getattr(p, "sku", p.id),
                "name": p.name,
                "on_hand": int(on_hand),
                "daily_demand": round(daily, 2),
                "cover": None if cover is None else round(cover, 1),
                "reco_qty": int(reco),
            })

    # Prioritize by lowest cover (risk first), then largest gap/reco
    recos.sort(key=lambda x: (x["cover"] if x["cover"] is not None else -1, -x["reco_qty"]))
    return recos[:limit]