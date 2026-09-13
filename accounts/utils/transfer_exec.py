from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import localdate
from accounts.models import Product, Branch, StockBatch, StockLedger


def execute_transfer(product_id, from_branch_id, to_branch_id, qty, user=None, reference=None):
    """
    Executes a branch-to-branch inventory transfer, creating:
    - OUT ledger entry (source branch)
    - IN ledger entry (destination branch)

    Returns a dict with transfer details.
    """

    product = Product.objects.get(pk=product_id)
    from_branch = Branch.objects.get(pk=from_branch_id)
    to_branch = Branch.objects.get(pk=to_branch_id)

    if from_branch_id == to_branch_id:
        return {"error": "Source and destination branches cannot be the same."}

    with transaction.atomic():
        remaining = Decimal(str(qty))
        batches = list(
            StockBatch.objects.select_for_update().filter(
                product=product,
                branch=from_branch,
                qty_on_hand__gt=0,
            ).filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gt=localdate())
            ).order_by("expiry_date", "batch_no")
        )
        available = sum((batch.qty_on_hand for batch in batches), Decimal("0"))
        if available < remaining:
            return {
                "error": f"Insufficient sellable stock. {available} available in {from_branch.name}, {qty} requested."
            }

        for source_batch in batches:
            if remaining <= 0:
                break
            moved_qty = min(source_batch.qty_on_hand, remaining)
            source_batch.qty_on_hand -= moved_qty
            source_batch.save(update_fields=["qty_on_hand"])
            destination_batch, _ = StockBatch.objects.get_or_create(
                product=product,
                branch=to_branch,
                batch_no=source_batch.batch_no,
                expiry_date=source_batch.expiry_date,
                defaults={"qty_on_hand": Decimal("0"), "buying_cost": source_batch.buying_cost},
            )
            destination_batch.qty_on_hand += moved_qty
            destination_batch.buying_cost = source_batch.buying_cost
            destination_batch.save(update_fields=["qty_on_hand", "buying_cost"])
            StockLedger.objects.create(
                product=product, branch=from_branch, batch=source_batch,
                qty_change=-moved_qty, unit_cost=source_batch.buying_cost,
                reason="TRANSFER_OUT", reference=reference or f"Transfer to {to_branch.name}", created_by=user,
            )
            StockLedger.objects.create(
                product=product, branch=to_branch, batch=destination_batch,
                qty_change=moved_qty, unit_cost=source_batch.buying_cost,
                reason="TRANSFER_IN", reference=reference or f"Transfer from {from_branch.name}", created_by=user,
            )
            remaining -= moved_qty

    return {
        "success": True,
        "product_id": product.id,
        "product": product.name,
        "sku": product.sku,
        "from": from_branch.name,
        "to": to_branch.name,
        "qty": qty,
        "available_before": available,
        "available_after": available - qty,

    }