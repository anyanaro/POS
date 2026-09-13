from decimal import Decimal

from django.test import TestCase

from accounts.models.product import Product
from accounts.models.price_rule import PriceRule
from accounts.models.org import Branch
from accounts.models.stock import StockBatch, StockLedger
from accounts.models.sales import SalesLine
from accounts.services.sales_engine import create_sale
from accounts.services.stock_adjustment_engine import adjust_stock
from django.core.exceptions import ValidationError
from accounts.services.analytics import sales_analytics, data_quality_report, supplier_price_intelligence
from accounts.utils.product_import import import_products, parse_product_workbook
from accounts.models.purchase import Supplier
from accounts.models.purchase import PurchaseHeader, PurchaseLine
from accounts.models.integration import BusinessCentralSync
from accounts.models.audit import AuditEvent
from io import BytesIO
from openpyxl import Workbook
from accounts.services.pricing_engine import calculate_price
from django.contrib.auth.models import User
from accounts.api.products import ProductSerializer
from accounts.api.suppliers import SupplierSerializer
from accounts.form.Insurance import InsuranceForm
from accounts.models.procurement import Requisition
from accounts.models.procurement_execution import GoodsReceipt, GoodsReceiptLine, SupplierInvoice
from accounts.models.transfer import TransferRequestHeader
from accounts.utils.stock import sellable_on_hand
from datetime import timedelta
from django.utils import timezone
from accounts.utils.transfer_exec import execute_transfer
import json


class RegistrationApprovalTests(TestCase):
	def test_registered_user_cannot_log_in_until_an_admin_activates_them(self):
		response = self.client.post("/register/", {
			"username": "pending-user",
			"email": "pending@example.com",
			"full_name": "Pending User",
			"phone": "0700000000",
			"password1": "Strong-pass-123!",
			"password2": "Strong-pass-123!",
		}, secure=True)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], "/login/")
		user = User.objects.get(username="pending-user")
		self.assertFalse(user.is_active)
		self.assertFalse(self.client.login(username="pending-user", password="Strong-pass-123!"))

		user.is_active = True
		user.save(update_fields=["is_active"])
		self.assertTrue(self.client.login(username="pending-user", password="Strong-pass-123!"))


class BusinessCentralNumberTests(TestCase):
	def test_product_supplier_and_insurance_require_bc_number(self):
		product = ProductSerializer(data={
			"name": "BC Product",
			"buying_cost": "10.00",
			"unit_price": "20.00",
		})
		supplier = SupplierSerializer(data={"name": "BC Supplier"})
		insurance = InsuranceForm(data={"name": "BC Insurance"})

		self.assertFalse(product.is_valid())
		self.assertIn("bc_number", product.errors)
		self.assertFalse(supplier.is_valid())
		self.assertIn("bc_number", supplier.errors)
		self.assertFalse(insurance.is_valid())
		self.assertIn("bc_number", insurance.errors)


class RequisitionLineEntryTests(TestCase):
	def test_requisition_create_saves_multiple_product_lines(self):
		user = User.objects.create_user(username="requisition-user", password="test-password")
		branch = Branch.objects.create(code="REQ", name="Requisition Branch")
		first_product = Product.objects.create(
			sku="REQ-001",
			bc_number="BC-REQ-001",
			name="First Requisition Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
		)
		second_product = Product.objects.create(
			sku="REQ-002",
			bc_number="BC-REQ-002",
			name="Second Requisition Product",
			buying_cost=Decimal("6.0000"),
			unit_price=Decimal("12.0000"),
		)
		self.client.force_login(user)
		session = self.client.session
		session["active_branch_id"] = branch.id
		session.save()

		response = self.client.post("/procurement/requisitions/new/", {
			"required_date": "2026-09-15",
			"remarks": "Two product test",
			"product_id[]": [str(first_product.id), str(second_product.id)],
			"qty_requested[]": ["2", "3.5"],
		}, secure=True)

		self.assertEqual(response.status_code, 302)
		requisition = Requisition.objects.get()
		self.assertEqual(requisition.lines.count(), 2)
		self.assertEqual(
			set(requisition.lines.values_list("product_id", "qty_requested")),
			{(first_product.id, Decimal("2.0000")), (second_product.id, Decimal("3.5000"))},
		)


class SupplierInvoiceReceiptTests(TestCase):
	def test_invoice_includes_uninvoiced_receipts_from_all_branches(self):
		user = User.objects.create_user(username="invoice-user", password="test-password")
		first_branch = Branch.objects.create(code="INV-A", name="Invoice Branch A")
		second_branch = Branch.objects.create(code="INV-B", name="Invoice Branch B")
		supplier = Supplier.objects.create(name="Invoice Supplier", bc_number="BC-INVOICE-SUPPLIER")
		product = Product.objects.create(
			sku="INV-001",
			bc_number="BC-INVOICE-PRODUCT",
			name="Invoice Product",
			buying_cost=Decimal("10.0000"),
			unit_price=Decimal("20.0000"),
		)
		purchase_order = PurchaseHeader.objects.create(
			branch=first_branch,
			created_by=user,
			supplier=supplier,
			purchase_date="2026-09-10",
			total=Decimal("50.00"),
		)
		purchase_line = PurchaseLine.objects.create(
			header=purchase_order,
			product=product,
			qty=Decimal("5.0000"),
			buying_cost=Decimal("10.0000"),
			line_total=Decimal("50.0000"),
		)
		first_receipt = GoodsReceipt.objects.create(
			po=purchase_order, branch=first_branch, supplier=supplier,
			received_by=user, receipt_mode="ORIGINAL_BRANCHES", status="RECEIVED",
		)
		second_receipt = GoodsReceipt.objects.create(
			po=purchase_order, branch=second_branch, supplier=supplier,
			received_by=user, receipt_mode="ORIGINAL_BRANCHES", status="RECEIVED",
		)
		first_line = GoodsReceiptLine.objects.create(
			receipt=first_receipt, po_line=purchase_line, product=product,
			ordered_qty=Decimal("5.0000"), received_qty=Decimal("2.0000"), batch_no="A-001",
		)
		second_line = GoodsReceiptLine.objects.create(
			receipt=second_receipt, po_line=purchase_line, product=product,
			ordered_qty=Decimal("5.0000"), received_qty=Decimal("3.0000"), batch_no="B-001",
		)
		self.client.force_login(user)

		response = self.client.get(f"/procurement/grn/{first_receipt.id}/invoice/", secure=True)

		self.assertEqual(response.status_code, 302)
		invoice = SupplierInvoice.objects.get()
		self.assertEqual(invoice.purchase_order, purchase_order)
		self.assertEqual(invoice.lines.count(), 2)
		self.assertEqual(invoice.total_amount, Decimal("50.00"))
		first_line.refresh_from_db()
		second_line.refresh_from_db()
		self.assertEqual(first_line.invoiced_qty, Decimal("2.0000"))
		self.assertEqual(second_line.invoiced_qty, Decimal("3.0000"))


class TransferRequestTests(TestCase):
	def test_transfer_request_requires_available_source_stock(self):
		user = User.objects.create_user(username="transfer-user", password="test-password")
		from_branch = Branch.objects.create(code="TRF-A", name="Transfer Source")
		to_branch = Branch.objects.create(code="TRF-B", name="Transfer Destination")
		product = Product.objects.create(
			sku="TRF-001",
			bc_number="BC-TRF-001",
			name="Transfer Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
		)
		StockLedger.objects.create(
			product=product, branch=from_branch, qty_change=Decimal("5.0000"),
			unit_cost=Decimal("5.0000"), reason=StockLedger.IN, reference="TEST-STOCK",
		)
		StockBatch.objects.create(
			product=product, branch=from_branch, batch_no="VALID-TRANSFER",
			qty_on_hand=Decimal("5.0000"), buying_cost=Decimal("5.0000"),
			expiry_date=timezone.localdate() + timedelta(days=30),
		)
		expired_product = Product.objects.create(
			sku="TRF-EXPIRED", bc_number="BC-TRF-EXPIRED", name="Expired Transfer Product",
			buying_cost=Decimal("5.0000"), unit_price=Decimal("10.0000"),
		)
		StockBatch.objects.create(
			product=expired_product, branch=from_branch, batch_no="EXPIRED-TRANSFER",
			qty_on_hand=Decimal("7.0000"), buying_cost=Decimal("5.0000"),
			expiry_date=timezone.localdate() - timedelta(days=1),
		)
		self.client.force_login(user)
		create_page = self.client.get("/transfers/create/", secure=True)
		self.assertEqual(create_page.status_code, 200)
		self.assertContains(create_page, "transfer-product-options")
		self.assertContains(create_page, "data-dynamic-table=\"true\"")
		self.assertContains(create_page, "/api/transfer/products/")
		available_products = self.client.get(
			f"/api/transfer/products/?branch_id={from_branch.id}", secure=True
		).json()["results"]
		self.assertEqual([row["id"] for row in available_products], [product.id])
		stock_response = self.client.get(f"/api/branch/stock/{product.id}/", secure=True)
		self.assertEqual(stock_response.status_code, 200)
		self.assertEqual(stock_response.json()[str(from_branch.id)], 5)
		suggested_request = self.client.post(
			"/api/transfer/suggestions/request/",
			data=json.dumps({
				"items": [{
					"product_id": product.id,
					"from_branch_id": from_branch.id,
					"to_branch_id": to_branch.id,
					"qty": "2",
				}],
			}),
			content_type="application/json",
			secure=True,
		)
		self.assertEqual(suggested_request.status_code, 200)
		self.assertEqual(suggested_request.json()["created"], 1)
		self.assertEqual(TransferRequestHeader.objects.count(), 1)

		response = self.client.post(
			"/api/transfer/request/",
			data=json.dumps({
				"from_branch_id": from_branch.id,
				"to_branch_id": to_branch.id,
				"items": [{"product_id": product.id, "qty": "3"}],
			}),
			content_type="application/json",
			secure=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()["success"])

		rejected = self.client.post(
			"/api/transfer/request/",
			data=json.dumps({
				"from_branch_id": from_branch.id,
				"to_branch_id": to_branch.id,
				"items": [{"product_id": product.id, "qty": "6"}],
			}),
			content_type="application/json",
			secure=True,
		)
		self.assertEqual(rejected.status_code, 400)
		self.assertIn("Only 5.0000 units", rejected.json()["error"])

		result = execute_transfer(product.id, from_branch.id, to_branch.id, Decimal("3.0000"), user)
		self.assertTrue(result["success"])
		self.assertEqual(sellable_on_hand(product.id, from_branch.id), Decimal("2.0000"))
		self.assertEqual(sellable_on_hand(product.id, to_branch.id), Decimal("3.0000"))


class InventoryStatusTests(TestCase):
	def test_inventory_status_shows_expired_and_low_usable_quantities(self):
		user = User.objects.create_user(username="inventory-user", password="test-password")
		branch = Branch.objects.create(code="INV", name="Inventory Branch")
		product = Product.objects.create(
			sku="INV-STATUS", bc_number="BC-INV-STATUS", name="Mixed Batch Product",
			buying_cost=Decimal("5.0000"), unit_price=Decimal("10.0000"),
		)
		expired_batch = StockBatch.objects.create(
			product=product, branch=branch, batch_no="EXPIRED", qty_on_hand=Decimal("5.0000"),
			buying_cost=Decimal("5.0000"), expiry_date=timezone.localdate() - timedelta(days=1),
		)
		valid_batch = StockBatch.objects.create(
			product=product, branch=branch, batch_no="VALID", qty_on_hand=Decimal("10.0000"),
			buying_cost=Decimal("5.0000"), expiry_date=timezone.localdate() + timedelta(days=30),
		)
		StockLedger.objects.create(product=product, branch=branch, batch=expired_batch, qty_change=Decimal("5.0000"), unit_cost=Decimal("5.0000"), reason=StockLedger.IN)
		StockLedger.objects.create(product=product, branch=branch, batch=valid_batch, qty_change=Decimal("10.0000"), unit_cost=Decimal("5.0000"), reason=StockLedger.IN)
		self.client.force_login(user)
		session = self.client.session
		session["active_branch_id"] = branch.id
		session.save()

		response = self.client.get("/inventory/", secure=True)

		self.assertContains(response, "Expired: 5")
		self.assertContains(response, "Low: 10")


class TransferSuggestionTests(TestCase):
	def test_transfer_suggestions_include_sellable_stock_only(self):
		user = User.objects.create_user(username="suggestion-user", password="test-password")
		from_branch = Branch.objects.create(code="SG-A", name="Suggestion Source")
		to_branch = Branch.objects.create(code="SG-B", name="Suggestion Destination")
		product = Product.objects.create(
			sku="SG-001", bc_number="BC-SG-001", name="Suggestion Product",
			buying_cost=Decimal("5.0000"), unit_price=Decimal("10.0000"),
			reorder_level=Decimal("10.0000"),
		)
		StockBatch.objects.create(
			product=product, branch=from_branch, batch_no="VALID", qty_on_hand=Decimal("25.0000"),
			buying_cost=Decimal("5.0000"), expiry_date=timezone.localdate() + timedelta(days=30),
		)
		StockBatch.objects.create(
			product=product, branch=from_branch, batch_no="EXPIRED", qty_on_hand=Decimal("25.0000"),
			buying_cost=Decimal("5.0000"), expiry_date=timezone.localdate() - timedelta(days=1),
		)
		self.client.force_login(user)

		response = self.client.get("/inventory/transfer-suggestions/", secure=True)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Suggestion Product")
		self.assertContains(response, "25.00")


class PricingEngineTests(TestCase):
	def setUp(self):
		self.product = Product.objects.create(
			sku="TEST-PRICE",
			bc_number="BC-TEST-PRICE",
			name="Pricing Test Product",
			buying_cost=Decimal("100.0000"),
			unit_price=Decimal("100.0000"),
			min_margin_pct=Decimal("10.00"),
			max_margin_pct=Decimal("20.00"),
		)

	def test_minimum_margin_bound_is_enforced(self):
		result = calculate_price(self.product.sku, Decimal("1"))

		self.assertEqual(result["unit_price"], Decimal("110.0000"))

	def test_maximum_margin_bound_is_enforced(self):
		PriceRule.objects.create(
			product=self.product,
			percentage=Decimal("-30.00"),
			min_qty=Decimal("1.00"),
		)

		result = calculate_price(self.product.sku, Decimal("1"))

		self.assertEqual(result["unit_price"], Decimal("120.0000"))

	def test_base_price_is_quantized_to_four_decimal_places(self):
		result = calculate_price(self.product.sku, Decimal("1"))

		self.assertEqual(result["unit_price"], Decimal("110.0000"))


class SalesEngineTests(TestCase):
	def test_sellable_stock_excludes_expired_batches(self):
		branch = Branch.objects.create(code="EXP", name="Expiry Branch")
		product = Product.objects.create(
			sku="TEST-EXPIRY",
			bc_number="BC-TEST-EXPIRY",
			name="Expiry Test Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
		)
		StockBatch.objects.create(
			product=product, branch=branch, batch_no="EXPIRED",
			qty_on_hand=Decimal("11.0000"), buying_cost=Decimal("5.0000"),
			expiry_date=timezone.localdate() - timedelta(days=1),
		)
		StockBatch.objects.create(
			product=product, branch=branch, batch_no="VALID",
			qty_on_hand=Decimal("9.0000"), buying_cost=Decimal("5.0000"),
			expiry_date=timezone.localdate() + timedelta(days=30),
		)

		self.assertEqual(sellable_on_hand(product.id, branch.id), Decimal("9.0000"))

	def test_stock_adjustment_cannot_create_negative_balance(self):
		from django.contrib.auth.models import User

		user = User.objects.create_user(username="adjuster", password="test")
		branch = Branch.objects.create(code="ADJ", name="Adjustment Branch")
		product = Product.objects.create(
			sku="TEST-ADJUST",
			bc_number="BC-TEST-ADJUST",
			name="Adjustment Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
		)
		batch = StockBatch.objects.create(
			product=product,
			branch=branch,
			batch_no="ADJ-BATCH",
			qty_on_hand=Decimal("1.0000"),
			buying_cost=Decimal("5.0000"),
		)

		with self.assertRaises(ValidationError):
			adjust_stock(product, branch, batch, Decimal("-2"), "TEST", user)

		adjust_stock(product, branch, batch, Decimal("1"), "TEST", user)
		self.assertTrue(AuditEvent.objects.filter(action="STOCK_ADJUSTMENT", entity_id=str(batch.id)).exists())

	def test_sale_preserves_margin_price_and_reduces_fefo_stock(self):
		from django.contrib.auth.models import User

		user = User.objects.create_user(username="cashier", password="test")
		branch = Branch.objects.create(code="TST", name="Test Branch")
		product = Product.objects.create(
			sku="TEST-SALE",
			bc_number="BC-TEST-SALE",
			name="Sales Test Product",
			buying_cost=Decimal("100.0000"),
			unit_price=Decimal("100.0000"),
			min_margin_pct=Decimal("10.00"),
			max_margin_pct=Decimal("20.00"),
		)
		batch = StockBatch.objects.create(
			product=product,
			branch=branch,
			batch_no="TEST-BATCH",
			qty_on_hand=Decimal("5.0000"),
			buying_cost=Decimal("80.0000"),
		)

		sale = create_sale(
			cashier=user,
			branch=branch,
			pos_terminal="TEST",
			items=[{"sku": product.sku, "qty": "2"}],
			tenders=[{"type": "CASH", "amount": "220"}],
		)

		batch.refresh_from_db()
		line = SalesLine.objects.get(header=sale)
		self.assertEqual(batch.qty_on_hand, Decimal("3.0000"))
		self.assertEqual(line.unit_price, Decimal("110.0000"))
		self.assertEqual(sale.total, Decimal("220.0000"))


class AdvancedFeatureTests(TestCase):
	def test_data_quality_flags_zero_cost_product(self):
		product = Product.objects.create(
			sku="TEST-QUALITY",
			bc_number="BC-TEST-QUALITY",
			name="Quality Product",
			buying_cost=Decimal("0.0000"),
			unit_price=Decimal("10.0000"),
		)

		findings = data_quality_report()

		self.assertTrue(any(finding["product"].id == product.id for finding in findings))

	def test_supplier_price_intelligence_aggregates_purchase_costs(self):
		from django.contrib.auth.models import User

		user = User.objects.create_user(username="supplier-intel", password="test")
		branch = Branch.objects.create(code="SPI", name="Supplier Intelligence")
		supplier = Supplier.objects.create(name="Intel Supplier", bc_number="BC-TEST-SUPPLIER")
		product = Product.objects.create(
			sku="TEST-SUPPLIER-PRICE",
			bc_number="BC-TEST-SUPPLIER-PRICE",
			name="Supplier Price Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
		)
		purchase = PurchaseHeader.objects.create(
			branch=branch,
			created_by=user,
			supplier=supplier,
			purchase_date="2026-09-01",
			total=Decimal("20.00"),
		)
		PurchaseLine.objects.create(
			header=purchase,
			product=product,
			qty=Decimal("2"),
			buying_cost=Decimal("10.0000"),
			line_total=Decimal("20.0000"),
		)

		rows = supplier_price_intelligence(product.id)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["average_cost"], Decimal("10.0000"))

	def test_sales_analytics_filters_by_user_and_limits_products(self):
		from django.contrib.auth.models import User

		first_user = User.objects.create_user(username="first-analytics", password="test")
		second_user = User.objects.create_user(username="second-analytics", password="test")
		branch = Branch.objects.create(code="FLT", name="Filter Branch")
		product = Product.objects.create(
			sku="TEST-FILTER",
			bc_number="BC-TEST-FILTER",
			name="Filter Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
			min_margin_pct=Decimal("0.00"),
			max_margin_pct=Decimal("100.00"),
		)
		StockBatch.objects.create(
			product=product,
			branch=branch,
			batch_no="FLT-BATCH",
			qty_on_hand=Decimal("10.0000"),
			buying_cost=Decimal("5.0000"),
		)
		create_sale(first_user, branch, "FLT", [{"sku": product.sku, "qty": "1"}], [{"type": "CASH", "amount": "10"}])
		create_sale(second_user, branch, "FLT", [{"sku": product.sku, "qty": "1"}], [{"type": "CASH", "amount": "10"}])

		result = sales_analytics(branch.id, limit=1, user_id=first_user.id)

		self.assertEqual(len(result["products"]), 1)
		self.assertEqual(result["products"][0]["units"], Decimal("1.0000"))
		self.assertEqual(len(result["users"]), 1)
		self.assertEqual(result["users"][0]["header__cashier__username"], first_user.username)

	def test_sales_analytics_calculates_product_margin(self):
		from django.contrib.auth.models import User

		user = User.objects.create_user(username="analytics", password="test")
		branch = Branch.objects.create(code="ANL", name="Analytics Branch")
		product = Product.objects.create(
			sku="TEST-ANALYTICS",
			bc_number="BC-TEST-ANALYTICS",
			name="Analytics Product",
			buying_cost=Decimal("5.0000"),
			unit_price=Decimal("10.0000"),
			min_margin_pct=Decimal("0.00"),
			max_margin_pct=Decimal("100.00"),
		)
		StockBatch.objects.create(
			product=product,
			branch=branch,
			batch_no="ANL-BATCH",
			qty_on_hand=Decimal("10.0000"),
			buying_cost=Decimal("5.0000"),
		)
		PriceRule.objects.create(
			product=product,
			percentage=Decimal("-100.00"),
			min_qty=Decimal("1.00"),
		)
		create_sale(
			cashier=user,
			branch=branch,
			pos_terminal="ANL",
			items=[{"sku": product.sku, "qty": "2"}],
			tenders=[{"type": "CASH", "amount": "20"}],
		)

		result = sales_analytics(branch.id, limit=10)

		self.assertEqual(result["products"][0]["units"], Decimal("2.0000"))
		self.assertEqual(result["products"][0]["gross_profit"], Decimal("10.0000"))

	def test_product_import_dry_run_does_not_create_records(self):
		supplier = Supplier.objects.create(name="Import Supplier", bc_number="BC-TEST-IMPORT-SUPPLIER")
		workbook = Workbook()
		sheet = workbook.active
		sheet.append(["bc_number", "name", "buying_cost", "unit_price", "supplier", "reorder_level", "reorder_qty"])
		sheet.append(["BC-TEST-IMPORT-PRODUCT", "Imported Product", 5, 10, supplier.name, 2, 5])
		upload = BytesIO()
		workbook.save(upload)
		upload.seek(0)

		result = import_products(upload, commit=False)

		self.assertEqual(result["errors"], [])
		self.assertEqual(result["preview"][0]["name"], "Imported Product")
		self.assertFalse(Product.objects.filter(bc_number="BC-TEST-IMPORT-PRODUCT").exists())

	def test_product_import_requires_and_preserves_bc_number(self):
		workbook = Workbook()
		sheet = workbook.active
		sheet.append(["bc_number", "name", "unit_price"])
		sheet.append(["BC-ITEM-0001", "BC Imported Product", 10])
		upload = BytesIO()
		workbook.save(upload)
		upload.seek(0)

		rows, errors = parse_product_workbook(upload)

		self.assertEqual(errors, [])
		self.assertEqual(rows[0]["bc_number"], "BC-ITEM-0001")
		upload.seek(0)
		result = import_products(upload, commit=True)
		product = Product.objects.get(bc_number="BC-ITEM-0001")
		self.assertEqual(result["created"], 1)
		self.assertTrue(product.sku.startswith("SKU-"))

	def test_business_central_queue_is_idempotent(self):
		first = BusinessCentralSync.objects.create(
			entity_type="SALE",
			entity_id="sale-1",
			payload={"total": "10.00"},
		)
		from accounts.integrations.business_central import queue_sync

		second = queue_sync("SALE", "sale-1", {"total": "11.00"})

		self.assertEqual(first.pk, second.pk)
		self.assertEqual(BusinessCentralSync.objects.count(), 1)
