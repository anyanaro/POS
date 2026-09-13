from django.db import models
from .product import Product

class PriceRule(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    active = models.BooleanField(default=True)

    def apply(self, unit_price, qty):
        if qty >= self.min_qty:
            return unit_price * (1 - (self.percentage / 100))
        return unit_price