from accounts.models.procurement import (
    SupplierQuotationLine
    )

def get_best_quote(product):

    quotes = []

    for quote_line in (
        SupplierQuotationLine.objects
        .filter(product=product)
    ):

        quotes.append(
            (
                quote_line.quoted_cost,
                quote_line
            )
        )

    quotes.sort()

    return quotes[0][1] if quotes else None