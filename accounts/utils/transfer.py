from accounts.models import Product, Branch
from accounts.utils.stock import on_hand
from datetime import timedelta
from django.utils.timezone import localdate
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce


DEC_FIELD = DecimalField(max_digits=18, decimal_places=2)

def branch_daily_demand(product_id, branch_id, days=14):
    from accounts.models import SalesLine
    today = localdate()
    since = today - timedelta(days=days)

    total = (
        SalesLine.objects
        .filter(product_id=product_id,
                header__branch_id=branch_id,
                header__created_at__date__gte=since)
        .aggregate(v=Coalesce(Sum("qty"), Value(0, output_field=DEC_FIELD)))
    )["v"] or 0

    return float(total) / max(1, days)


def build_transfer_matrix(target_cover_days=14):
    """
    Returns a list of transfer suggestions:
    [
        {
            "product_id": 4,
            "product": "Paracetamol",
            "from_branch": "Kisumu",
            "to_branch": "Nairobi",
            "qty": 12,
            "from_stock": 35,
            "to_stock": 2,
            "to_demand": 5.5,
            "to_cover": 0.4
        }
    ]
    """

    out = []

    products = Product.objects.filter(active=True).only("id", "sku", "name")
    branches = list(Branch.objects.all())

    for p in products:
        # collect branch-level stock + demand for this product
        bstats = []
        for b in branches:
            stock = on_hand(p.id, b.id)
            demand = branch_daily_demand(p.id, b.id)

            cover = (stock / demand) if demand > 0 else 9999

            bstats.append({
                "branch": b,
                "stock": stock,
                "demand": demand,
                "cover": cover,
                "needed": max(0, int(target_cover_days * demand - stock)) if demand > 0 else 0,
                "surplus": max(0, stock - int(target_cover_days * demand)) if demand > 0 else stock
            })

        # branches needing stock
        needy = [x for x in bstats if x["needed"] > 0]
        # branches able to give stock
        surplus = [x for x in bstats if x["surplus"] > 0]

        # match needy branches with surplus branches
        for need in needy:
            qty_needed = need["needed"]

            # try to take from each surplus branch
            for sup in surplus:
                if qty_needed <= 0:
                    break
                if sup["surplus"] <= 0:
                    continue

                qty_transfer = min(qty_needed, sup["surplus"])

                out.append({
                    "product_id": p.id,
                    "product": p.name,
                    "sku": p.sku,

                    "from_branch": sup["branch"].name,
                    "from_branch_id": sup["branch"].id,
                    "from_stock": sup["stock"],

                    "to_branch": need["branch"].name,
                    "to_branch_id": need["branch"].id,
                    "to_stock": need["stock"],

                    "to_demand": round(need["demand"], 2),
                    "to_cover": round(need["cover"], 2),

                    "qty": qty_transfer,
                })

                # update counters
                sup["surplus"] -= qty_transfer
                qty_needed -= qty_transfer

    return out