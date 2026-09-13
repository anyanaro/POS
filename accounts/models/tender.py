from django.db import models
from .sales import SalesHeader

class Tender(models.Model):
    CASH = "CASH"
    CARD = "CARD"
    MOBILE = "MOBILE"

    TYPES = [
        (CASH, "Cash"),
        (CARD, "Card"),
        (MOBILE, "Mobile Money"),
    ]

    header = models.ForeignKey(SalesHeader, on_delete=models.CASCADE, related_name="tenders")
    tender_type = models.CharField(max_length=20, choices=TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)