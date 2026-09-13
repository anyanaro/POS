from accounts.models import (
    ProductCostHistory
)

def post_invoice(invoice):

    for line in invoice.lines.all():

        ProductCostHistory.objects.create(
            product=line.product,
            supplier=invoice.supplier,
            invoice_no=invoice.invoice_no,
            cost_price=line.cost_price,
            trade_price=line.trade_price
        )

        product = line.product

        product.buying_cost = (
            line.cost_price
        )

        product.trade_price = (
            line.trade_price
        )

        product.save()

    invoice.status = "POSTED"
    invoice.save()