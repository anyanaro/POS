# accounts/services/sale_reversal_engine.py
from django.db import transaction
from accounts.models.sales import SalesHeader
from accounts.models.sale_reversal import SaleReversal
from accounts.models.stock import StockLedger, StockBatch

@transaction.atomic
def reverse_sale(sale_id: str, user):
    header = SalesHeader.objects.select_related("branch").get(sale_id=sale_id)

    if SaleReversal.objects.filter(header=header).exists():
        raise Exception("Sale already reversed")

    for line in header.lines.all():
        if line.batch:
            batch = line.batch

            batch.qty_on_hand += line.qty
            batch.save(update_fields=["qty_on_hand"])

            StockLedger.objects.create(
                product=line.product,
                branch=header.branch,
                batch=batch,
                qty_change=line.qty,
                reason="IN",
                reference=f"REV-{sale_id}",
            )

    SaleReversal.objects.create(
        header=header,
        reversed_by=user,
        reason="Manual reversal"
    )

    header.status = "REVERSED"
    header.save(update_fields=["status"])

    return True