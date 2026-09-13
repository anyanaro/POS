# accounts/utils/stock.py

from decimal import Decimal
from django.db.models import F, Q, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from accounts.models import Branch, StockBatch, StockLedger

DEC_FIELD = DecimalField(max_digits=18, decimal_places=2)

def active_branch(request):
    """
    Returns active branch object from session.
    """
    bid = request.session.get("active_branch_id")
    return Branch.objects.filter(pk=bid).first() if bid else None


def on_hand(product_id, branch_id=None):
    """
    Return the ledger balance for inventory reporting and transfer workflows.
    """
    qs = StockLedger.objects.filter(product_id=product_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    val = qs.aggregate(
        v=Coalesce(Sum("qty_change"), Value(0, output_field=DEC_FIELD))
    )["v"] or 0

    return int(val)


def sellable_on_hand(product_id, branch_id=None):
    """Return unexpired physical batch stock available for POS checkout."""
    batches = StockBatch.objects.filter(
        product_id=product_id,
        qty_on_hand__gt=0,
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gt=timezone.localdate())
    )
    if branch_id:
        batches = batches.filter(branch_id=branch_id)

    return batches.aggregate(
        total=Coalesce(Sum("qty_on_hand"), Value(0, output_field=DEC_FIELD))
    )["total"] or Decimal("0")




def average_purchase_cost(product_id, branch_id=None):
    """
    Return the weighted average cost of inventory currently on hand.
    """

    batches = StockBatch.objects.filter(
        product_id=product_id,
        qty_on_hand__gt=0,
        buying_cost__gt=0,
    )

    if branch_id:
        batches = batches.filter(branch_id=branch_id)

    totals = batches.aggregate(
        quantity=Sum("qty_on_hand"),
        value=Sum(F("qty_on_hand") * F("buying_cost")),
    )

    quantity = totals["quantity"] or Decimal("0")
    value = totals["value"] or Decimal("0")

    return value / quantity if quantity > 0 else Decimal("0")

#def average_purchase_cost(product_id, branch_id=None):
   # """Return the weighted average unit cost of received stock."""
   # qs = StockLedger.objects.filter(
   #     product_id=product_id,
   #     reason=StockLedger.IN,
    #    qty_change__gt=0,
    #    unit_cost__gt=0,
   # )
   # if branch_id:
    #    qs = qs.filter(branch_id=branch_id)

   # totals = qs.aggregate(
   #     quantity=Sum("qty_change"),
   #     value=Sum(F("qty_change") * F("unit_cost")),
   # )
  #  quantity = totals["quantity"] or Decimal("0")
  #  if quantity > 0:
  #      return Decimal(totals["value"]) / Decimal(quantity)

   # batches = StockBatch.objects.filter(
   #     product_id=product_id,
  #      qty_on_hand__gt=0,
   # )
   # if branch_id:
   #     batches = batches.filter(branch_id=branch_id)
   # fallback = batches.aggregate(
   #     quantity=Sum("qty_on_hand"),
    #    value=Sum(F("qty_on_hand") * F("buying_cost")),
   # )
   # quantity = fallback["quantity"] or Decimal("0")
   # return (
   #     Decimal(fallback["value"]) / Decimal(quantity)
   #     if quantity > 0
   #     else Decimal("0")
  #  )