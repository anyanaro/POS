# accounts/views_products.py
from django.shortcuts import render, get_object_or_404
from accounts.models import Product, Supplier

def product_list_html(request):
    suppliers = Supplier.objects.filter(active=True)
    """Renders HTML table; data comes from /api/products/ via JS."""
    return render(request, "accounts/products_manage_list.html", {
        "suppliers": suppliers
    })

def product_add_html(request):
    suppliers = Supplier.objects.filter(active=True)
    """Renders HTML form; submit via JS to /api/products/."""
    return render(request, "accounts/product_form.html", {
        "mode": "add",
        "api_url": "/api/products/",
        "product": None,
        "suppliers": suppliers
    })

def product_edit_html(request, pk: int):
    suppliers = Supplier.objects.filter(active=True)
    prod = get_object_or_404(Product, pk=pk)
    return render(request, "accounts/product_form.html", {
        "mode": "edit",
        "api_url": f"/api/products/{pk}/",
        "product": prod,
        "suppliers": suppliers
    })

def product_delete_html(request, pk: int):
    prod = get_object_or_404(Product, pk=pk)
    suppliers = Supplier.objects.filter(active=True)
    return render(request, "accounts/product_confirm_delete.html", {
        "api_url": f"/api/products/{pk}/",
        "product": prod,
        "suppliers": suppliers
    })