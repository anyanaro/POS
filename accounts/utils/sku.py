# accounts/utils/sku.py
from django.db import transaction
from accounts.models.sku_counter import SkuCounter

def next_sku(prefix: str = "SKU", width: int = 6) -> str:
    """
    Allocate the next SKU with an atomic per-prefix counter.
    Example: prefix='SKU', width=6 -> 'SKU-000001'
    """
    key = (prefix or "SKU").upper().strip()

    with transaction.atomic():
        counter, _ = SkuCounter.objects.select_for_update().get_or_create(
            key=key,
            defaults={"last": 0}
        )
        counter.last += 1
        counter.save(update_fields=["last"])
        return f"{key}-{str(counter.last).zfill(width)}"
        
def supplier_prefix(supplier) -> str:
    if not supplier or not getattr(supplier, "name", None):
        return "SKU"
    # e.g., 'Nakuru Wholesalers' -> 'NAK'
    import re
    letters = re.sub(r"[^A-Za-z0-9]", "", supplier.name).upper()
    return (letters[:3] or "SKU")