# accounts/services/sales_engine.py
from decimal import Decimal
from django.db import transaction

from accounts.models.sales import SalesHeader, SalesLine
from accounts.models.tender import Tender
from accounts.services.pricing_engine import calculate_price
from accounts.services.stock_engine import allocate_fefo, reduce_stock_allocations
from accounts.models.product import Product
from accounts.models.org import Branch

@transaction.atomic
def create_sale(cashier, branch: Branch, pos_terminal: str, items: list, tenders: list):
    """
    items: [{"sku": "P001", "qty": 2}]
    tenders: [{"type": "CASH", "amount": 1000}]
    """
    header = SalesHeader.objects.create(
        cashier=cashier,
        branch=branch,
        pos_terminal=pos_terminal,
    )

    total = Decimal("0")
    tax_total = Decimal("0")

    for item in items:
        sku = item["sku"]
        qty = Decimal(item["qty"])

        line_data = calculate_price(sku, qty)
        product = line_data["product"]

        # FEFO allocation
        allocations = allocate_fefo(product, branch, qty)
        reduce_stock_allocations(product, branch, allocations,
                                reason="OUT", reference=str(header.sale_id))

        # Weighted cost
        total_cost = sum([Decimal(a["qty"]) * Decimal(a["cost"]) for a in allocations])
        avg_cost = (total_cost / qty).quantize(Decimal("0.0001"))

        primary_batch = allocations[0]["batch"] if allocations else None

        SalesLine.objects.create(
            header=header,
            product=product,
            batch=primary_batch,
            qty=qty,
            unit_price=line_data["unit_price"],
            discount=line_data["discount"],
            line_total=line_data["line_total"],
            line_cost=avg_cost,
        )

        total += line_data["line_total"]
        tax_total += line_data["tax_amount"]

    # Save tenders
    for t in tenders:
        Tender.objects.create(
            header=header,
            tender_type=t["type"],
            amount=Decimal(t["amount"]),
        )

    header.total = total
    header.tax_total = tax_total
    header.save(update_fields=["total", "tax_total"])

    return header