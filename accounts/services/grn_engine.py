from decimal import Decimal

from accounts.models import (
    StockBatch,
    StockLedger,
)

def post_goods_receipt(grn):

    if grn.status == "VERIFIED":
        return

    for line in grn.lines.all():

        batch, created = (
            StockBatch.objects.get_or_create(
                branch=grn.branch,
                product=line.product,
                batch_no=line.batch_no,
                defaults={
                    "expiry_date":
                        line.expiry_date,
                    "qty_on_hand": 0
                }
            )
        )

        batch.qty_on_hand += (
            line.received_qty
        )
        batch.buying_cost = line.po_line.buying_cost

        batch.save()

        StockLedger.objects.create(
            product=line.product,
            branch=grn.branch,
            batch=batch,
            qty_change=line.received_qty,
            unit_cost=line.po_line.buying_cost,
            reason="IN",
            reference=f"GRN-{grn.id}"
        )

    grn.status = "VERIFIED"
    grn.save()