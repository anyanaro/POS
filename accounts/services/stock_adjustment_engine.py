# accounts/services/stock_adjustment_engine.py
from decimal import Decimal
from django.db import transaction

from accounts.models.stock import StockBatch, StockLedger
from accounts.models.stock_adjustment import StockAdjustment
from accounts.models.product import Product
from accounts.models.org import Branch
from accounts.models.audit import AuditEvent
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

@transaction.atomic
def adjust_stock(product: Product, branch: Branch, batch: StockBatch,
                 qty_change: Decimal, reason: str, user: User):
    """
    Handles both positive and negative adjustments.
    """
    qty_change = Decimal(qty_change)
    new_qty = batch.qty_on_hand + qty_change
    if new_qty < 0:
        raise ValidationError(
            f"Adjustment would make {product} stock negative. Available: {batch.qty_on_hand}."
        )
    batch.qty_on_hand = new_qty
    batch.save(update_fields=["qty_on_hand"])

    StockAdjustment.objects.create(
        product=product,
        branch=branch,
        batch=batch,
        qty_change=qty_change,
        reason=reason,
        created_by=user,
    )

    StockLedger.objects.create(
        product=product,
        branch=branch,
        batch=batch,
        qty_change=qty_change,
        unit_cost=batch.buying_cost,
        reason=f"ADJUST: {reason}",
        reference=f"ADJ-{batch.id}",
    )
    AuditEvent.objects.create(
        actor=user,
        action="STOCK_ADJUSTMENT",
        entity_type="StockBatch",
        entity_id=str(batch.id),
        branch=branch,
        details={
            "product_id": product.id,
            "qty_change": str(qty_change),
            "reason": reason,
        },
    )