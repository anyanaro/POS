from django.utils import timezone

from accounts.models import (
    PurchaseHeader,
    PurchaseLine,
)


def create_po_from_quote(
    quote,
    branch,
    user,
):
    po = PurchaseHeader.objects.create(
        branch=branch,
        supplier=quote.supplier,
        purchase_date=timezone.now().date(),
        created_by=user,
        status="APPROVED"
    )

    total = 0

    for line in quote.lines.all():

        amount = (
            line.qty *
            line.quoted_cost
        )

        PurchaseLine.objects.create(
            header=po,
            product=line.product,
            qty=line.qty,
            buying_cost=line.quoted_cost,
            line_total=amount
        )

        total += amount

    po.total = total
    po.save()

    return po