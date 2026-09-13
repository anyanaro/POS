# accounts/services/procurement_engine.py

from accounts.models import Requisition


def submit_requisition(requisition):

    if requisition.status != "DRAFT":
        raise Exception(
            "Only draft requisitions can be submitted."
        )

    requisition.status = "SUBMITTED"
    requisition.save()

    return requisition

def approve_requisition(requisition):

    requisition.status = "APPROVED"
    requisition.save()

    return requisition