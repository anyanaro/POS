from django.contrib import admin
from django.db.models import Sum
from accounts.models.sales import SalesHeader
from accounts.models.stock import StockBatch

def pos_dashboard(request):
    total_sales = SalesHeader.objects.all().aggregate(Sum("total"))["total__sum"] or 0
    stock_value = sum([(b.qty_on_hand * b.buying_cost) for b in StockBatch.objects.all()])

    return {
        "total_sales": total_sales,
        "stock_value": stock_value,
    }