from collections import defaultdict

from accounts.models import (
    Requisition,
    ConsolidatedOrder,
    ConsolidatedOrderLine,
)


def generate_consolidated_order(
    supplier,
    user,
):
    requisitions = (
        Requisition.objects
        .filter(status="APPROVED")
        .prefetch_related("lines")
    )

    totals = defaultdict(float)

    for req in requisitions:

        for line in req.lines.all():

            totals[line.product_id] += float(
                line.qty_approved
            )

    order = ConsolidatedOrder.objects.create(
        supplier=supplier,
        created_by=user,
        status="RFQ"
    )

    for product_id, qty in totals.items():

        ConsolidatedOrderLine.objects.create(
            order=order,
            product_id=product_id,
            qty=qty
        )

    requisitions.update(
        status="CONSOLIDATED"
    )

    return order