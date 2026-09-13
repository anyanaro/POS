from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from django.utils import timezone



from accounts.admin_site import my_admin_site
from django.contrib import admin
from accounts.models.profile import Profile
from accounts.models.purchase import Supplier, PurchaseHeader, PurchaseLine
from accounts.models import (
    Profile,
    Branch, UserBranch,
    Supplier,
    Product, PriceRule,
    StockBatch, StockLedger,
    SalesHeader, SalesLine, Tender,
    SaleReversal,
    StockAdjustment,
    Expense,
    VendorLedgerEntry,
)
from accounts.models.procurement import (
    Requisition,
    RequisitionLine,
    ConsolidatedOrder,
    ConsolidatedOrderLine,
    SupplierQuotation,
    SupplierQuotationLine,
    ProductCostHistory,
)


# Built-ins
my_admin_site.register(User, UserAdmin)
my_admin_site.register(Group, GroupAdmin)

admin.site.register(Requisition)
admin.site.register(RequisitionLine)
admin.site.register(ConsolidatedOrder)
admin.site.register(ConsolidatedOrderLine)
admin.site.register(SupplierQuotation)
admin.site.register(SupplierQuotationLine)
admin.site.register(ProductCostHistory)

# Profile
@admin.register(Profile, site=my_admin_site)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "phone", "role")
    search_fields = ("user__username", "full_name", "phone")
    list_filter = ("role",)


# Branch
@admin.register(Branch, site=my_admin_site)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    search_fields = ("code", "name")
    list_filter = ("active",)

# UserBranch
@admin.register(UserBranch, site=my_admin_site)
class UserBranchAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "is_default")
    list_filter = ("is_default", "branch")
    search_fields = ("user__username",)

# Supplier
@admin.register(Supplier, site=my_admin_site)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("code", "bc_number", "name", "phone", "active")
    list_filter = ("active",)
    search_fields = ("code", "bc_number", "name", "phone")

# Product
@admin.register(Product, site=my_admin_site)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku", "bc_number", "name", "unit_price", "buying_cost",
        "margin_display", "active", "image_preview"
    )
    search_fields = ("sku", "bc_number", "name", "barcode")
    list_filter = ("active", "supplier")
    readonly_fields = ("image_preview",)

    def margin_display(self, obj):
        try:
            margin = ((obj.unit_price - obj.buying_cost) / (obj.buying_cost or 1)) * 100
            return f"{margin:.1f}%"
        except Exception:
            return "N/A"
    margin_display.short_description = "Margin %"

    def image_preview(self, obj):
        if not getattr(obj, "image", None):
            return "No image"
        # IMPORTANT: use real HTML tags here, not HTML entities
        return format_html(
            '<img src="{}" style="height:50px;width:50px;object-fit:cover;border-radius:5px;" />',
            obj.image.url
        )

# PriceRule
@admin.register(PriceRule, site=my_admin_site)
class PriceRuleAdmin(admin.ModelAdmin):
    list_display = ("product", "percentage", "min_qty", "active")
    list_filter = ("active", "percentage")
    search_fields = ("product__name", "product__sku")

# StockBatch
@admin.register(StockBatch, site=my_admin_site)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = (
        "product", "branch", "batch_no", "expiry_date",
        "qty_on_hand", "buying_cost", "expiry_status"
    )

    def expiry_status(self, obj):
        if not obj.expiry_date:
            return "No expiry"
        today = timezone.now().date()
        diff = (obj.expiry_date - today).days
        if diff < 0:
            color = "red"
            txt = f"Expired ({abs(diff)}d)"
        elif diff < 30:
            color = "orange"
            txt = f"Expiring ({diff}d)"
        else:
            color = "green"
            txt = f"{diff}d remaining"
        # IMPORTANT: use real <span> tag here
        return format_html('<span style="color:{};">{}</span>', color, txt)

    expiry_status.short_description = "Expiry Status"

    def increment_stock(self, request, queryset):
        from accounts.services.stock_adjustment_engine import adjust_stock
        for batch in queryset:
            adjust_stock(
                product=batch.product,
                branch=batch.branch,
                batch=batch,
                qty_change=1,
                reason="ADMIN +1",
                user=request.user
            )
        self.message_user(request, "Stock increased by 1 for selected batches")

    def decrement_stock(self, request, queryset):
        from accounts.services.stock_adjustment_engine import adjust_stock
        for batch in queryset:
            adjust_stock(
                product=batch.product,
                branch=batch.branch,
                batch=batch,
                qty_change=-1,
                reason="ADMIN -1",
                user=request.user
            )
        self.message_user(request, "Stock decreased by 1 for selected batches")

    actions = [increment_stock, decrement_stock]

# StockLedger
@admin.register(StockLedger, site=my_admin_site)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = ("product", "branch", "batch", "qty_change", "reason", "reference", "created_at")
    list_filter = ("branch", "reason")
    search_fields = ("product__sku", "reference")

# SalesHeader + inlines
class SalesLineInline(admin.TabularInline):
    model = SalesLine
    extra = 0
    readonly_fields = ("product", "batch", "qty", "unit_price", "discount", "line_total", "line_cost")

class TenderInline(admin.TabularInline):
    model = Tender
    extra = 0

@admin.register(SalesHeader, site=my_admin_site)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ("sale_id", "branch", "cashier", "total", "status", "created_at")
    list_filter = ("branch", "status", "created_at")
    search_fields = ("sale_id", "cashier__username")
    inlines = [SalesLineInline, TenderInline]

# SaleReversal
@admin.register(SaleReversal, site=my_admin_site)
class SaleReversalAdmin(admin.ModelAdmin):
    list_display = ("header", "reversed_by", "reason", "created_at")
    list_filter = ("created_at",)
    search_fields = ("header__sale_id", "reversed_by__username")

# accounts/admin.py (append)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    list_filter = ("active",)
    search_fields = ("code", "name", "email", "phone")

class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    fk_name = "header"
    extra = 0
    readonly_fields = ("line_total",)

@admin.register(PurchaseHeader)
class PurchaseHeaderAdmin(admin.ModelAdmin):
    list_display = ("purchase_id", "branch", "supplier", "reference", "purchase_date", "total", "status", "created_at")
    list_filter = ("branch", "supplier", "status")
    search_fields = ("purchase_id", "reference")
    inlines = [PurchaseLineInline]

# StockAdjustment
@admin.register(StockAdjustment, site=my_admin_site)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "branch", "batch", "qty_change", "reason", "created_by", "created_at")
    list_filter = ("branch", "reason")
    search_fields = ("product__sku", "batch__batch_no")

# Expense
@admin.register(Expense, site=my_admin_site)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("branch", "date", "category", "amount", "created_by")
    list_filter = ("branch", "category")
    search_fields = ("category",)

# VendorLedgerEntry
@admin.register(VendorLedgerEntry, site=my_admin_site)
class VendorLedgerAdmin(admin.ModelAdmin):
    list_display = ("supplier", "branch", "entry_type", "amount", "reference", "created_at")
    list_filter = ("entry_type", "supplier", "branch")
    search_fields = ("supplier__name", "reference")


class UserBranchInline(admin.TabularInline):
    model = UserBranch
    extra = 1

class UserAdmin(UserAdmin):
    inlines = [UserBranchInline]
    list_display = ("username", "email", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
        

admin.site.unregister(User)
admin.site.register(User, UserAdmin)