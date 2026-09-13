# accounts/views_suppliers.py
from django.shortcuts import render, get_object_or_404
from accounts.models import Supplier



def supplier_list_html(request):
    """
    Legacy: separate manage list page (no KPIs).
    If you no longer use this, you can remove this view and route.
    """
    return render(request, "accounts/suppliers_manage_list.html")


def supplier_add_html(request):
    """Add Supplier form (AJAX posts to /api/suppliers/)."""
    return render(
        request,
        "accounts/supplier_form.html",
        {
            "mode": "add",
            "api_url": "/api/suppliers/",
            "supplier": None,
        },
    )


def supplier_edit_html(request, pk: int):
    """Edit Supplier form (AJAX PUT/PATCH to /api/suppliers/{id}/)."""
    supplier = get_object_or_404(Supplier, pk=pk)
    return render(
        request,
        "accounts/supplier_form.html",
        {
            "mode": "edit",
            "api_url": f"/api/suppliers/{pk}/",
            "supplier": supplier,
        },
    )


def supplier_delete_html(request, pk: int):
    """Delete confirmation (AJAX DELETE to /api/suppliers/{id}/)."""
    supplier = get_object_or_404(Supplier, pk=pk)
    return render(
        request,
        "accounts/supplier_confirm_delete.html",
        {
            "api_url": f"/api/suppliers/{pk}/",
            "supplier": supplier,
        },
    )


