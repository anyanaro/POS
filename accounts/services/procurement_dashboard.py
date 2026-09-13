from models.procurement_execution import GoodsReceipt, SupplierInvoice
from models.procurement import Requisition

def procurement_metrics():

    return {

        "pending_requisitions":
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

        "pending_invoices":
            SupplierInvoice.objects.filter(
                status="DRAFT"
            ).count()
    }