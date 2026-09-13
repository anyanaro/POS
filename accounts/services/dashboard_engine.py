

from accounts.models import (
    Requisition,
    GoodsReceipt,
    SupplierInvoice,
)

def procurement_dashboard():

    return {

        "submitted_requisitions":
            Requisition.objects.filter(
                status="SUBMITTED"
            ).count(),

        "urgent_requests":
            Requisition.objects.filter(
                urgent=True,
                status="SUBMITTED"
            ).count(),

        "pending_grns":
            GoodsReceipt.objects.filter(
                status="RECEIVED"
            ).count(),

        "draft_invoices":
            SupplierInvoice.objects.filter(
                status="DRAFT"
            ).count(),
    }