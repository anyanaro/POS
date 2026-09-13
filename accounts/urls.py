from django.urls import path, include
from django.contrib.auth.decorators import login_required

# Views
from accounts import views as auth_views
from accounts.view import views as page_views
from accounts.view.sales_views import (
    SubmitSaleView, SaleDetailView, ReverseSaleView, ReversalListApiView,InsuranceSchemeApiView,
    SetActiveBranchView, SalesExportCSV, SalesExportExcel,
    LedgerExportCSV, LedgerExportExcel,
    StockMovementExportCSV, StockMovementExportExcel,
    ExpiryBatchExportCSV, ExpiryBatchExportExcel
)
from accounts.view.stock_views import (
    StockBalancesView, StockBatchListView, StockLedgerView,
    StockAdjustmentView, PhysicalStockCountView
)
from accounts.view.core_views import (
    ProductListView, SupplierListView, PriceRuleListView, ExpenseCreateView
)
from accounts.view.views_purchase import (
    PurchaseSubmitView, PurchaseListView, PurchaseDetailView,
    PurchaseCreateView, InventoryExportCSV, InventoryExportExcel,
    PurchaseExportCSV, PurchaseExportExcel, UrgentRequisitionView,
    UrgentPurchaseListView, UrgentPurchaseEditView,
)
from accounts.view.report_views import ProfitLossView
from accounts.view.physical_stock_views import physical_stock_take, physical_stock_take_export, physical_stock_take_approve, physical_stock_take_cancel
from accounts.view.product_import_views import product_import_page, product_import_template
from accounts.view.integration_views import business_central_dashboard
from accounts.view.integration_views import queue_business_central_sync, process_business_central_sync
from accounts.view.branch_views import SwitchBranchView, UserBranchesView
from accounts.view.vendor_views import VendorPostEntryView, VendorLedgerListView
from accounts.view.sales_quote_views import sales_quote, product_last_price, sales_quote_pdf
from accounts.ai.views import ask_ai
from accounts.view.Insurance import insurance_list, insurance_create, insurance_edit, insurance_scheme_list, insurance_scheme_create, insurance_scheme_edit
# HTML product/supplier views + DRF API
from accounts import views_products as pviews
from accounts import views_suppliers as sviews
from accounts.api import products as papi
from accounts.api import suppliers as sapi
from rest_framework.routers import DefaultRouter
from django.contrib.auth import views as dj_auth_views

# Transfer System
from accounts.view.views import (
    stk_push, payment_status, mpesa_callback, stock_check, barcode_image,transfer_create,
    restock_api, transfer_suggestions, transfer_execute, transfer_pdf,reject_transfer,
    transfer_history, approve_transfer, transfer_approvals,transfer_dashboard,transfer_request,
    transfer_stats_api, branch_stock_api, transfer_available_products, execute_approved_transfer,create_transfer_request,
    stock_transfer_suggestions, create_suggested_transfer_requests
)

from accounts.view.procurement_views import *
from accounts.view.inventory_views import *
from accounts.view.finance_views import *
from accounts.view.report_views import *
from accounts.view.branch_views import *

app_name = "accounts"

urlpatterns = [

    # ---------------- AUTH ----------------
    path("login/", auth_views.login_view, name="login"),
    path("logout/", auth_views.logout_view, name="logout"),
    path("register/", auth_views.register_view, name="register"),
    path("home/", auth_views.home_view, name="home"),
    path("", auth_views.home_redirect, name="home-redirect"),

    # ---------------- DASHBOARD & PAGES ----------------
    path("dashboard/", page_views.dashboard, name="dashboard"),
    path("inventory/profit-reports/", page_views.inventory_profit_reports, name="inventory-profit-reports"),
    path("sales/", page_views.sales, name="sales"),
    path("products/", page_views.products, name="products"),
   path("products/generate-barcodes/",page_views.generate_missing_barcodes,name="generate-missing-barcodes",),
    path("suppliers/manage/", page_views.suppliers_dashboard, name="suppliers-manage"),
    path("reports/", page_views.reports, name="reports"),
    path("reports/analytics/", analytics_dashboard, name="analytics-dashboard"),
    path("api/reports/analytics/", analytics_api, name="analytics-api"),
    path("api/integrations/business-central/queue/", queue_business_central_sync, name="bc-queue"),
    path("api/integrations/business-central/process/", process_business_central_sync, name="bc-process"),
    path("api/ask-ai/", ask_ai, name="ask-ai"),
    
         # Insurance
    path("insurances/", insurance_list, name="insurance_list"),
    path("insurances/new/", insurance_create, name="insurance_create"),
    path("insurances/<int:pk>/edit/", insurance_edit, name="insurance_edit"),
    
    # Insurance Schemes
    path("insurance-schemes/", insurance_scheme_list, name="insurance_scheme_list"),
    path("insurance-schemes/new/", insurance_scheme_create, name="insurance_scheme_create"),
    path("insurance-schemes/<int:pk>/edit/", insurance_scheme_edit, name="insurance_scheme_edit"),
    
    # Procurement
    path("procurement/requisitions/",requisition_list,name="requisitions"),
    path("procurement/consolidated-orders/",consolidated_order_list,name="consolidated-orders"),
    path("procurement/consolidated-orders/create/",create_consolidated_order,name="create-consolidated-order"),
    path("procurement/consolidated-orders/<int:pk>/",consolidated_order_detail,name="consolidated-order-detail"),
    path("procurement/consolidated-orders/<int:pk>/approve/",consolidated_order_approve,name="consolidated-order-approve"),
    path("procurement/reorder/",reorder_list,name="reorder-list"),
    path("procurement/rfq/<int:pk>/comparison/",quotation_comparison,name="quotation-comparison"),
    path("procurement/quotation/<int:pk>/award/",award_supplier,name="award-supplier"),
    path("procurement/quotation-line/<int:pk>/award/",award_quotation_line,name="award-quotation-line"),
    path("procurement/consolidated-orders/<int:pk>/rfq/",create_rfq,name="create-rfq"),
    path("procurement/quotation/<int:pk>/purchase-order/",generate_purchase_order,name="generate-purchase-order"),
    path("procurement/rfqs/<int:pk>/entry/",quotation_entry,name="quotation-entry"),
    path("procurement/requisitions/<int:pk>/approve/",requisition_approve,name="requisition-approve"),
    path("procurement/rfqs/",rfq_list,name="rfqs"),
    path("procurement/purchase-orders/",purchase_order_list,name="purchase-orders"),
    path("procurement/goods-receipts/",goods_receipt_list,name="goods-receipts"),
    path("procurement/supplier-invoices/",supplier_invoice_list,name="supplier-invoices"),
    path("returns/",returns_list,name="returns"),
    path("stock-receipts/",stock_receipts,name="stock-receipts"),
    path("procurement/requisitions/new/",requisition_create,name="requisition-create"),
    path("procurement/requisitions/<int:pk>/edit/",requisition_form,name="requisition-edit"),
    path("procurement/requisitions/<int:pk>/delete/",requisition_delete,name="requisition-delete"),
    path("procurement/purchase-orders/<int:pk>/",purchase_order_detail,name="purchase-order-detail"),
    path("procurement/purchase-orders/<int:pk>/pdf/",purchase_order_pdf,name="purchase-order-pdf"),
    path("procurement/purchase-orders/<int:pk>/grn/",create_grn,name="create-grn"),
    path("procurement/goods-receipts/<int:pk>/",goods_receipt_detail,name="goods-receipt-detail"),
    path("procurement/grn/<int:pk>/invoice/",create_supplier_invoice,name="create-supplier-invoice"),
    path("procurement/supplier-invoices/<int:pk>/",supplier_invoice_detail,name="supplier-invoice-detail"),
    path("procurement/supplier-invoices/<int:pk>/pdf/",supplier_invoice_pdf,name="supplier-invoice-pdf"),

    # Finance
    path("finance/supplier-ledger/",supplier_ledger,name="supplier-ledger"),
    path("finance/invoice-posting/",invoice_posting,name="invoice-posting"),
    path("finance/payments/",supplier_payments,name="payments"),
    path("finance/cost-analysis/",cost_analysis,name="cost-analysis"),
    path("finance/invoices/<int:pk>/post/",post_supplier_invoice,name="post-supplier-invoice"),
    path("finance/invoices/<int:pk>/send-finance/",send_invoice_finance,name="send-invoice-finance"),
    path("finance/invoices/<int:pk>/payment/",create_supplier_payment,name="create-supplier-payment"),
    path("finance/payments/",supplier_payments,name="supplier-payments"),
    
    # Reports
    path("reports/stock-aging/",stock_aging,name="stock-aging"),
    path("reports/procurement-savings/",procurement_savings,name="procurement-savings"),
    path("reports/supplier-performance/",supplier_performance,name="supplier-performance"),
    path("reports/margin-analysis/",margin_analysis,name="margin-analysis"),
    path("reports/data-quality/", data_quality, name="data-quality"),
    path("reports/supplier-price-intelligence/", supplier_price_intelligence_report, name="supplier-price-intelligence"),
    path("reports/abc-analysis/", abc_analysis_report, name="abc-analysis"),
    path("reports/forecast-accuracy/", forecast_accuracy_report, name="forecast-accuracy"),
    path("reports/sales-forecasting/", sales_forecasting, name="sales-forecasting"),
    path("reports/procurement-plan/", procurement_plan, name="procurement-plan"),

    # ---------------- INVENTORY ----------------
    path("inventory/", page_views.inventory, name="inventory"),
    path("inventory/physical-stock-take/", physical_stock_take, name="physical-stock-take"),
    path("inventory/physical-stock-take/export/", physical_stock_take_export, name="physical-stock-take-export"),
    path("inventory/physical-stock-take/approve/", physical_stock_take_approve, name="physical-stock-take-approve"),
    path("inventory/physical-stock-take/cancel/", physical_stock_take_cancel, name="physical-stock-take-cancel"),
    path("inventory/product-import/", product_import_page, name="product-import"),
    path("inventory/product-import/template/", product_import_template, name="product-import-template"),
    path("integrations/business-central/", business_central_dashboard, name="business-central"),
    path("inventory/branch-stock-availability/", branch_stock_availability, name="branch-stock-availability"),
    path( "inventory/batches/",batch_tracking,name="batch-tracking"),
    path("inventory/expiry/",expiry_monitoring,name="expiry-monitoring"),
    path("inventory/batches/export/",export_batches_excel,name="export_batches_excel",),
    path("inventory/expiry/export/csv/", ExpiryBatchExportCSV.as_view(), name="expiry-batch-export-csv"),
    path("inventory/expiry/export/excel/", ExpiryBatchExportExcel.as_view(), name="expiry-batch-export-excel"),
    path("inventory/export/csv/", InventoryExportCSV.as_view(), name="inventory-export-csv"),
    path("inventory/export/excel/", InventoryExportExcel.as_view(), name="inventory-export-excel"),

    # ---------------- SALES ----------------
    path("sales/quote/", sales_quote, name="sales-quote"),
    path("sales/quote/pdf/", sales_quote_pdf, name="sales-quote-pdf"),
    path("api/products/<int:pk>/last-price/", product_last_price, name="product-last-price"),
    path("sales/submit/", SubmitSaleView.as_view(), name="sales-submit"),
    path("insurance/schemes/",InsuranceSchemeApiView.as_view(),name="insurance-schemes",),
    path("sales/<uuid:sale_id>/", SaleDetailView.as_view(), name="sales-detail"),
    path("sales/reverse/", ReverseSaleView.as_view(), name="sales-reverse"),
    path("sales/reversals/", ReversalListApiView.as_view(), name="sales-reversals"),
    path("sales/export/csv/", SalesExportCSV.as_view(), name="sales-export-csv"),
    path("sales/export/excel/", SalesExportExcel.as_view(), name="sales-export-excel"),

    # ---------------- PURCHASES ----------------
    path("purchases/submit/", PurchaseSubmitView.as_view(), name="purchase-submit"),
    path("purchases/", PurchaseListView.as_view(), name="purchases"),
    path("purchases/<uuid:purchase_id>/", PurchaseDetailView.as_view(), name="purchase-detail"),
    path("purchases/new/", PurchaseCreateView.as_view(), name="purchase-new"),
    path("purchases/urgent/new/", UrgentRequisitionView.as_view(), name="urgent-requisition"),
    path("purchases/urgent/", UrgentPurchaseListView.as_view(), name="urgent-purchases"),
    path("purchases/urgent/<uuid:purchase_id>/", UrgentPurchaseEditView.as_view(), name="urgent-purchase-edit"),
    path("purchases/export/csv/", PurchaseExportCSV.as_view(), name="purchases-export-csv"),
    path("purchases/export/excel/", PurchaseExportExcel.as_view(), name="purchases-export-excel"),

    # ---------------- PRODUCT HTML CRUD ----------------
    path("products/manage/", login_required(pviews.product_list_html), name="product-manage"),
    path("products/manage/add/", login_required(pviews.product_add_html), name="product-add"),
    path("products/manage/<int:pk>/edit/", login_required(pviews.product_edit_html), name="product-edit"),
    path("products/manage/<int:pk>/delete/", login_required(pviews.product_delete_html), name="product-delete"),

    # ---------------- SUPPLIERS ----------------
    path("suppliers/manage/", login_required(sviews.supplier_list_html), name="supplier-manage"),
    path("suppliers/manage/add/", login_required(sviews.supplier_add_html), name="supplier-add"),
    path("suppliers/manage/<int:pk>/edit/", login_required(sviews.supplier_edit_html), name="supplier-edit"),
    path("suppliers/manage/<int:pk>/delete/", login_required(sviews.supplier_delete_html), name="supplier-delete"),

    # ---------------- MPESA ----------------
    path("api/mpesa/stkpush/", stk_push, name="mpesa-stk"),
    path("api/mpesa/status/<str:checkout_id>/", payment_status),
    path("mpesa/callback/", mpesa_callback),

    # ---------------- BARCODE ----------------
    path("barcode/<str:sku>/", barcode_image, name="barcode-image"),

    # ---------------- STOCK ----------------
    path("stock/balances/", StockBalancesView.as_view(), name="stock-balances"),
    path("stock/check/", stock_check, name="stock-check"),
    path("stock/batches/", StockBatchListView.as_view(), name="stock-batches"),
    path("stock/ledger/", StockLedgerView.as_view(), name="stock-ledger"),
    path("stock/adjust/", StockAdjustmentView.as_view(), name="stock-adjust"),
    path("stock/physical-count/", PhysicalStockCountView.as_view(), name="stock-physical-count"),
    path("ledger/export/csv/", LedgerExportCSV.as_view(), name="ledger-export-csv"),
    path("ledger/export/excel/", LedgerExportExcel.as_view(), name="ledger-export-excel"),
    path("stock-movement/export/csv/", StockMovementExportCSV.as_view(), name="stock-movement-export-csv"),
    path("stock-movement/export/excel/", StockMovementExportExcel.as_view(), name="stock-movement-export-excel"),

    # ---------------- RESTOCK & TRANSFERS ----------------
    path("api/restock/", restock_api, name="branch-restock"),
    path("api/transfer/", transfer_suggestions, name="transfer-suggestions"),
    path("api/transfer/execute/", transfer_execute, name="transfer-execute"),
    path("api/transfer/execute-approved/", execute_approved_transfer, name="transfer-execute-approved"),
    path("api/transfer/approve/", approve_transfer, name="transfer-approve"),
    path("api/transfer/pdf/", transfer_pdf, name="transfer-pdf"),
    path("api/transfer/stats/", transfer_stats_api, name="transfer-stats"),
    path("api/branch/stock/<int:product_id>/", branch_stock_api, name="branch-stock"),
    path("api/transfer/products/", transfer_available_products, name="transfer-available-products"),
    path("transfers/history/", transfer_history, name="transfer-history"),
    path("transfers/approvals/", transfer_approvals, name="transfer-approvals"),
    path("transfers/",transfer_dashboard,name="transfers"),
    path("transfers/request/",transfer_request,name="transfer-request"),
    path("inventory/transfer-suggestions/", stock_transfer_suggestions, name="stock-transfer-suggestions"),
    path("api/transfer/suggestions/request/", create_suggested_transfer_requests, name="create-suggested-transfer-requests"),
    path("api/transfer/reject/",reject_transfer,name="transfer-reject"),
    path("transfers/create/",transfer_create,name="transfer-create"),
    path("api/transfer/request/",create_transfer_request, name="transfer-request-save"),

    # ---------------- MASTER DATA ----------------
    path("products/list/", ProductListView.as_view(), name="products-list"),
    path("suppliers/list/", SupplierListView.as_view(), name="suppliers-list"),
    path("pricerules/", PriceRuleListView.as_view(), name="pricerules-list"),

    # ---------------- EXPENSES ----------------
    path("expenses/", ExpenseCreateView.as_view(), name="expense-create"),

    # ---------------- VENDOR LEDGER ----------------
    path("vendor/post-entry/", VendorPostEntryView.as_view(), name="vendor-post-entry"),
    path("vendor/ledger/", VendorLedgerListView.as_view(), name="vendor-ledger-list"),

    # ---------------- BRANCHES ----------------
    path("branches/mine/", UserBranchesView.as_view(), name="branches-mine"),
    path("branches/switch/", SwitchBranchView.as_view(), name="branch-switch"),
    path("set-branch/", SetActiveBranchView.as_view(), name="set-branch"),

    # ---------------- PASSWORD RESET ----------------
    path("password_reset/", dj_auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset.html",
        email_template_name="accounts/password_reset_email.html",
    ), name="password_reset"),

    path("password_reset/done/", dj_auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html",
    ), name="password_reset_done"),

    path("reset/<uidb64>/<token>/", dj_auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
    ), name="password_reset_confirm"),

    path("reset/done/", dj_auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html",
    ), name="password_reset_complete"),
]

# ---------------- DRF ROUTER ----------------
router = DefaultRouter()
router.register(r"products", papi.ProductViewSet, basename="product")
router.register(r"suppliers", sapi.SupplierViewSet, basename="supplier")

urlpatterns += [path("api/", include(router.urls))]