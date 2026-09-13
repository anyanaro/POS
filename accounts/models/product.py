from django.db import models
from accounts.utils.sku import next_sku



class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True, blank=True)
    bc_number = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=50, blank=True, null=True)

    buying_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    min_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    max_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    trade_price = models.DecimalField(
    max_digits=12,
    decimal_places=4,
    default=0
    )
    reorder_level = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )
    reorder_qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0
    )
    supplier = models.ForeignKey(
        "accounts.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    active = models.BooleanField(default=True)
    image = models.ImageField(upload_to="product_images/", null=True, blank=True)

    def save(self, *args, **kwargs):
        if (not self.pk) and (not self.sku or not self.sku.strip()):
            self.sku = next_sku(prefix="SKU", width=6)
        else:
            if self.sku:
                self.sku = self.sku.strip().upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} – {self.name}"