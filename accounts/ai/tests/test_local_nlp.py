# accounts/ai/tests/test_local_nlp.py
from django.test import TestCase
from datetime import date
from decimal import Decimal
from accounts.models import Branch, Product
from accounts.ai.local_nlp import parse_intent_and_entities

class LocalNLPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Branches: include unique codes to avoid unique constraint errors.
        Branch.objects.get_or_create(name="Nakuru", defaults={"code": "NAK"})
        Branch.objects.get_or_create(name="Rome", defaults={"code": "ROM"})

        # Products: include required numeric fields (unit_price, buying_cost, etc.)
        Product.objects.create(
            sku="ABC-123",
            name="Premium Milk 1L",
            unit_price=Decimal("120.00"),
            buying_cost=Decimal("100.00"),
            active=True,
            # set other NOT NULL fields your model requires, e.g.:
            # tax_rate=Decimal("0.00"), msrp=Decimal("0.00"), etc.
        )
        Product.objects.create(
            sku="BREAD-500",
            name="Brown Bread 500g",
            unit_price=Decimal("60.00"),
            buying_cost=Decimal("45.00"),
            active=True,
            # tax_rate=Decimal("0.00"),
        )



    def test_top_products_synonyms(self):
        q = "Show me the top 5 items"
        parsed = parse_intent_and_entities(q)
        self.assertEqual(parsed["intent"], "top_products")

        q2 = "best selling products"
        parsed = parse_intent_and_entities(q2)
        self.assertEqual(parsed["intent"], "top_products")

    def test_low_stock_synonyms(self):
        q = "which items are low on stock?"
        parsed = parse_intent_and_entities(q)
        self.assertEqual(parsed["intent"], "low_stock")

        q2 = "any stock shortage?"
        parsed = parse_intent_and_entities(q2)
        self.assertEqual(parsed["intent"], "low_stock")

    def test_sales_today_and_date_range(self):
        today = date.today().isoformat()
        parsed = parse_intent_and_entities("sales today")
        self.assertEqual(parsed["intent"], "sales_today")
        self.assertIn("since", parsed["entities"])
        self.assertIn("until", parsed["entities"])
        self.assertEqual(parsed["entities"]["since"], today)
        self.assertEqual(parsed["entities"]["until"], today)

        parsed2 = parse_intent_and_entities("sales last 7 days")
        self.assertEqual(parsed2["intent"], "sales_today")  # maps to sales aggregation intent
        self.assertIn("since", parsed2["entities"])
        self.assertIn("until", parsed2["entities"])

    def test_branch_extraction(self):
        parsed = parse_intent_and_entities("which branch is best in Nakuru?")
        self.assertEqual(parsed["intent"], "branch_rank")
        self.assertEqual(parsed["entities"].get("branch"), "Nakuru")

    def test_product_extraction_by_sku(self):
        parsed = parse_intent_and_entities("How is ABC-123 performing today?")
        # Intent may be unknown due to phrasing, but product should be detected
        self.assertIsNotNone(parsed["entities"].get("product_sku"))

    def test_unknown_floor(self):
        parsed = parse_intent_and_entities("hello world")
        self.assertEqual(parsed["intent"], "unknown")