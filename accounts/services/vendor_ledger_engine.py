# accounts/services/vendor_ledger_engine.py
from decimal import Decimal
from accounts.models.vendor_ledger import VendorLedgerEntry
from accounts.models.purchase import Supplier
from accounts.models.org import Branch

def vendor_credit(supplier: Supplier, branch: Branch, amount: Decimal, ref: str):
    """
    Credit = money owed to vendor (AP increases)
    """
    VendorLedgerEntry.objects.create(
        supplier=supplier,
        branch=branch,
        entry_type=VendorLedgerEntry.CREDIT,
        amount=amount,
        reference=ref,
    )

def vendor_debit(supplier: Supplier, branch: Branch, amount: Decimal, ref: str):
    """
    Debit = payment to vendor (AP decreases)
    """
    VendorLedgerEntry.objects.create(
        supplier=supplier,
        branch=branch,
        entry_type=VendorLedgerEntry.DEBIT,
        amount=amount,
        reference=ref,
    )