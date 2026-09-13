# accounts/services/stock_engine.py
from decimal import Decimal
from django.db import transaction, models
from django.db.models import Case, When, Value, IntegerField

from accounts.models.stock import StockBatch, StockLedger
from accounts.models.product import Product
from accounts.models.org import Branch

def get_branch_stock_balances(branch: Branch):
    """
    Returns:
    [
        {"sku": "P001", "name":"Panadol", "total_qty":"120.00"},
        ...
    ]
    """
    aggregate = (
        StockBatch.objects
        .filter(branch=branch)
        .values("product__sku", "product__name")
        .annotate(total_qty=models.Sum("qty_on_hand"))
    )

    return [
        {
            "sku": row["product__sku"],
            "name": row["product__name"],
            "total_qty": row["total_qty"],
        }
        for row in aggregate
    ]

def _fefo_batches(product: Product, branch: Branch):
    """
    FEFO: earliest expiry first; null last
    """
    return (
        StockBatch.objects
        .filter(product=product, branch=branch, qty_on_hand__gt=0)
        .annotate(
            expiry_null=Case(
                When(expiry_date__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("expiry_null", "expiry_date", "batch_no")
    )

def allocate_fefo(product: Product, branch: Branch, qty_required: Decimal):
    allocations = []
    remaining = Decimal(qty_required)

    for batch in _fefo_batches(product, branch):
        if remaining <= 0:
            break

        take = min(batch.qty_on_hand, remaining)
        if take > 0:
            allocations.append({
                "batch": batch,
                "qty": take,
                "cost": Decimal(batch.buying_cost)
            })
            remaining -= take

    if remaining > 0:
        raise Exception(f"Insufficient stock for {product.sku} in branch {branch.code}")

    return allocations

@transaction.atomic
def reduce_stock_allocations(product: Product, branch: Branch, allocations, reason="OUT", reference=None):
    """
    Writes ledger and reduces batch.qty_on_hand
    """
    for entry in allocations:
        batch = entry["batch"]
        qty = Decimal(entry["qty"])

        batch.qty_on_hand = batch.qty_on_hand - qty
        batch.save(update_fields=["qty_on_hand"])

        StockLedger.objects.create(
            product=product,
            branch=branch,
            batch=batch,
            qty_change=-qty,
            unit_cost=batch.buying_cost,
            reason=reason,
            reference=reference,
        )