from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from accounts.models.procurement_execution import (
    SupplierInvoice,
    SupplierPayment
)
from django.db.models import Sum

@login_required
def accounts_payable_dashboard(request):

    unpaid = SupplierInvoice.objects.exclude(
        status="PAID"
    )

    total_payable = unpaid.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    return render(
        request,
        "accounts/finance/ap_dashboard.html",
        {
            "total_payable": total_payable,
            "unpaid": unpaid,
        }
    )
    

@login_required
def supplier_ledger(request):

    invoices = SupplierInvoice.objects.select_related(
        "supplier",
        "purchase_order",
        "grn"
    )

    return render(
        request,
        "accounts/finance/supplier_ledger.html",
        {
            "invoices": invoices
        }
    )


@login_required
def invoice_posting(request):

    invoices = (
        SupplierInvoice.objects
        .select_related("supplier")
        .filter(status="PAID")
        .order_by("-invoice_date")
    )

    return render(
        request,
        "accounts/finance/invoice_posting.html",
        {
            "invoices": invoices
        }
    )


@login_required
def supplier_payments(request):

    payments = SupplierPayment.objects.all()

    return render(
        request,
        "accounts/finance/payments.html",
        {
            "payments": payments
        }
    )


@login_required
def cost_analysis(request):

    return render(
        request,
        "accounts/finance/cost_analysis.html"
    )
    
@login_required
def post_supplier_invoice(request, pk):

    invoice = get_object_or_404(
        SupplierInvoice,
        pk=pk
    )

    if invoice.status == "DRAFT":

        invoice.status = "POSTED"

        invoice.save()

        messages.success(
            request,
            f"Invoice {invoice.invoice_no} posted successfully."
        )

    return redirect(
        "accounts:invoice-posting"
    )
    
@login_required
def send_invoice_finance(request, pk):

    invoice = get_object_or_404(
        SupplierInvoice,
        pk=pk
    )

    if invoice.status != "POSTED":

        messages.warning(
            request,
            "Invoice must be POSTED first."
        )

        return redirect(
            "accounts:supplier-invoice-detail",
            invoice.id
        )

    invoice.status = "SENT_FINANCE"

    invoice.save()

    invoice.purchase_order.status = "INVOICED"

    invoice.purchase_order.save()

    messages.success(
        request,
        "Invoice sent to Finance."
    )

    return redirect(
        "accounts:supplier-invoice-detail",
        invoice.id
    )

@login_required
def create_supplier_payment(request, pk):

    invoice = get_object_or_404(
        SupplierInvoice,
        pk=pk
    )
    
    if invoice.status == "PAID":

        messages.warning(
            request,
            "This invoice has already been paid."
        )

        return redirect(
            "accounts:supplier-invoice-detail",
            invoice.id
        )

    if request.method == "POST":

        payment = SupplierPayment.objects.create(

            invoice=invoice,

            payment_date=request.POST.get(
                "payment_date"
            ),

            amount=request.POST.get(
                "amount"
            ),

            payment_method=request.POST.get(
                "payment_method"
            ),

            reference=request.POST.get(
                "reference"
            ),

            paid_by=request.user
        )

        invoice.status = "PAID"

        invoice.paid_date = payment.payment_date

        invoice.paid_by = request.user

        invoice.save()

        invoice.purchase_order.status = "PAID"

        invoice.purchase_order.save()

        messages.success(
            request,
            "Supplier payment recorded."
        )

        return redirect(
            "accounts:supplier-payments"
        )

    return render(
        request,
        "accounts/finance/payment_form.html",
        {
            "invoice": invoice,
            "methods": SupplierPayment.PAYMENT_METHODS,
        }
    )