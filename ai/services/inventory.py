# ai/services/inventory.py
from datetime import date
from django.db.models import Sum
from accounts.models.stock import StockBatch
from accounts.models import StockLedger
from ai.models import Forecast
from datetime import timedelta

def stock_cover_days(branch_id, product_id):
    # Sum next 14 days of forecast demand
    demand = (Forecast.objects
              .filter(branch_id=branch_id, product_id=product_id, date__gte=date.today(), date__lt=date.today()+timedelta(days=14))
              .aggregate(total=Sum("yhat"))["total"] or 0) / 14.0
    if not demand or demand <= 0:
        return None
    on_hand = StockBatch.objects.filter(
        branch_id=branch_id,
        product_id=product_id,
    ).aggregate(total=Sum("qty_on_hand"))["total"] or 0
    return on_hand / demand