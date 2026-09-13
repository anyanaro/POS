# accounts/services/pricing_engine.py
from decimal import Decimal
from accounts.models.product import Product
from accounts.models.price_rule import PriceRule

MONEY_QUANTUM = Decimal("0.0001")

def _apply_rules(product: Product, qty: Decimal, candidate_price: Decimal) -> Decimal:
    rules = PriceRule.objects.filter(product=product, active=True)
    for rule in rules:
        candidate_price = rule.apply(candidate_price, qty)
    return candidate_price

def _enforce_margin_bounds(product: Product, candidate_price: Decimal) -> Decimal:
    buying = Decimal(product.buying_cost or 0)
    
    min_price = buying * (Decimal(1) + (Decimal(product.min_margin_pct) / 100))
    max_price = buying * (Decimal(1) + (Decimal(product.max_margin_pct) / 100))

    if candidate_price < min_price:
        return min_price.quantize(MONEY_QUANTUM)

    if candidate_price > max_price:
        return max_price.quantize(MONEY_QUANTUM)

    return candidate_price.quantize(MONEY_QUANTUM)

def calculate_price(sku: str, qty: Decimal):
    product = Product.objects.get(sku=sku)

    base_price = Decimal(product.buying_cost)
    price_after_rules = _apply_rules(product, qty, base_price)
    unit_price = _enforce_margin_bounds(product, price_after_rules)

    line_total = unit_price * qty
    tax_amount = line_total * (Decimal(product.tax_rate) / 100)

    return {
        "product": product,
        "unit_price": unit_price,
        "discount": base_price - unit_price,
        "line_total": line_total,
        "tax_amount": tax_amount,
    }