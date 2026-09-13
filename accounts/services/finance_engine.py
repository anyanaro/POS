from django.db import models

def post_payment(payment):

    invoice = payment.invoice

    paid = invoice.payments.aggregate(
        total=models.Sum("amount")
    )["total"] or 0

    if paid >= invoice.total_amount:

        invoice.status = "PAID"

        invoice.save()