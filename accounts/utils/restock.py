from accounts.models import Product, Branch
from accounts.utils.stock import on_hand
from datetime import timedelta
from django.utils.timezone import localdate
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce

DEC_FIELD = DecimalField(max_digits=18, decimal_places=2)

def branch_demand(product_id, branch_id, days=14):
    from accounts.models import SalesLine
    today = localdate()
    since = today - timedelta(days=days)

    total = (
        SalesLine.objects
        .filter(product_id=product_id, header__branch_id=branch_id,
                header__created_at__date__gte=since)
        .aggregate(v=Coalesce(Sum("qty"), Value(0, output_field=DEC_FIELD)))
    )["v"]

    return float(total or 0) / max(1, days)


def branch_restock_suggestions(target_days=14):
    """
    Returns list with:
    [
        {
            "product_id":..,
            "sku":..,
            "name":..,
            "branch_id":..,
            "branch_name":..,
            "on_hand":..,
            "daily_demand":..,
            "cover_days":..,
            "recommended_qty":..
        }
    ]
    """
    out = []

    for p in Product.objects.filter(active=True).only("id", "sku", "name"):
        for b in Branch.objects.all():
            stock = on_hand(p.id, b.id)
            demand = branch_demand(p.id, b.id)

            if demand <= 0:
                continue

            cover = stock / demand if demand > 0 else 999
            if cover < target_days:

                required = int((target_days * demand) - stock)
                if required <= 0:
                    continue

                out.append({
                    "product_id": p.id,
                    "sku": p.sku,
                    "name": p.name,
                    "branch_id": b.id,
                    "branch_name": b.name,
                    "on_hand": stock,
                    "daily_demand": round(demand, 2),
                    "cover_days": round(cover, 1),
                    "recommended_qty": required
                })

    out.sort(key=lambda x: (x["cover_days"], -x["recommended_qty"]))
    return out