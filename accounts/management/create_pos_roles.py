from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from accounts.models import (
    SalesHeader, StockAdjustment, SaleReversal,
    Expense, VendorLedgerEntry
)

class Command(BaseCommand):
    help = "Create default POS roles"

    def handle(self, *args, **kwargs):
        cashier, _ = Group.objects.get_or_create(name="Cashier")
        supervisor, _ = Group.objects.get_or_create(name="Supervisor")
        manager, _ = Group.objects.get_or_create(name="Manager")
        admin_group, _ = Group.objects.get_or_create(name="Admin")

        # Cashier: Can add sales only
        cashier.permissions.set(
            Permission.objects.filter(codename__startswith="add_salesheader")
        )

        # Supervisor
        supervisor.permissions.set(
            Permission.objects.filter(codename__in=[
                "add_salesheader", "add_salereversal", "add_stockadjustment"
            ])
        )

        # Manager: All POS models
        manager.permissions.set(
            Permission.objects.filter(content_type__app_label="pos")
        )

        # Admin: all model permissions
        admin_group.permissions.set(Permission.objects.all())

        self.stdout.write(self.style.SUCCESS("POS Roles created successfully"))