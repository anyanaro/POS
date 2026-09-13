# accounts/view/sales_quote_views.py

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

from accounts.models.product import Product
from accounts.models.sales import SalesLine


@login_required
def sales_quote(request):
    return render(request, "accounts/sales_quote.html")


@login_required
@require_GET
def product_last_price(request, pk):
    """Return the most recent unit price at which a product was sold."""

    last_line = (
        SalesLine.objects
        .filter(product_id=pk)
        .order_by("-header__created_at")
        .first()
    )

    last_price = str(last_line.unit_price) if last_line else None

    product = Product.objects.filter(pk=pk).first()

    fallback_price = (
        str(product.unit_price) if product else "0"
    )

    return JsonResponse({
        "product_id": pk,
        "last_price": last_price or fallback_price,
        "has_history": last_line is not None,
    })


@login_required
@require_POST
def sales_quote_pdf(request):
    """Generate a downloadable PDF quote for the selected items."""

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    customer_name = str(payload.get("customer_name") or "").strip()
    items = payload.get("items") or []

    if not isinstance(items, list) or not items:
        return JsonResponse({"error": "Add at least one item to the quote."}, status=400)

    parsed_items = []
    grand_total = Decimal("0")

    for raw in items:
        try:
            qty = Decimal(str(raw.get("qty", 0)))
            unit_price = Decimal(str(raw.get("unit_price", 0)))
        except (InvalidOperation, TypeError):
            return JsonResponse({"error": "Invalid quantity or price."}, status=400)

        if qty <= 0 or unit_price < 0:
            return JsonResponse({"error": "Invalid quantity or price."}, status=400)

        line_total = qty * unit_price
        grand_total += line_total

        parsed_items.append({
            "sku": str(raw.get("sku") or ""),
            "name": str(raw.get("name") or ""),
            "qty": qty,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="sales-quote.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "QuoteSubtitle",
        parent=styles["Normal"],
        alignment=1,
        textColor=colors.grey,
    )

    elements = [
        Paragraph("FARMA24 SALES QUOTE", title_style),
        Paragraph(
            f"Date: {payload.get('date') or ''}".strip() or " ",
            subtitle_style,
        ) if payload.get("date") else Spacer(1, 0),
        Spacer(1, 12),
        Paragraph(f"Customer: {customer_name or 'Walk-in customer'}", styles["Normal"]),
        Spacer(1, 16),
    ]

    data = [["SKU", "Product", "Qty", "Unit Price", "Line Total"]]

    for item in parsed_items:
        data.append([
            item["sku"],
            item["name"],
            str(item["qty"]),
            f'{item["unit_price"]:.2f}',
            f'{item["line_total"]:.2f}',
        ])

    data.append(["", "", "", "Grand Total", f"{grand_total:.2f}"])

    table = Table(data, colWidths=[70, 190, 50, 80, 80])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ])
    )

    elements.append(table)

    doc.build(elements)

    return response
