# accounts/view/procurement_views.py

from django.contrib.auth.decorators import login_required
from accounts.models.purchase import Supplier, PurchaseHeader, PurchaseLine 
from accounts.models.procurement_execution import (
    GoodsReceipt,GoodsReceiptLine,
    GoodsReceiptAllocation,
    SupplierInvoice,SupplierInvoiceLine
)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, F, Sum
from django.utils import timezone
from accounts.models.product import Product
from accounts.models.procurement import (
    Requisition,
    RequisitionLine,
    ConsolidatedOrder,
    ConsolidatedOrderLine,ConsolidatedAllocation,
    SupplierQuotation,SupplierQuotationLine
)
from django.urls import reverse
from urllib.parse import urlencode
from decimal import Decimal
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)
from django.db import transaction
from accounts.models.stock import StockBatch, StockLedger  
from reportlab.lib.styles import getSampleStyleSheet
from accounts.models.org import Branch
from datetime import date


def _reorder_candidates(request):
    branch_id = request.session.get("active_branch_id")
    candidates = []
    for product in Product.objects.filter(active=True).select_related("supplier").order_by("name"):
        stock = StockBatch.objects.filter(
            product=product,
            **({"branch_id": branch_id} if branch_id else {})
        ).aggregate(total=Sum("qty_on_hand"))["total"] or Decimal("0")
        level = Decimal(product.reorder_level or 0)
        if level <= 0 or stock > level:
            continue

        history = list(
            PurchaseLine.objects.filter(
                product=product,
                header__supplier__isnull=False,
                buying_cost__isnull=False,
            ).select_related("header__supplier").order_by("-header__purchase_date")[:12]
        )
        supplier_stats = {}
        for line in history:
            row = supplier_stats.setdefault(line.header.supplier_id, {
                "supplier": line.header.supplier,
                "purchases": 0,
                "quantity": Decimal("0"),
                "cost": Decimal("0"),
            })
            row["purchases"] += 1
            row["quantity"] += line.qty
            row["cost"] += line.buying_cost or Decimal("0")
        suppliers = []
        for row in supplier_stats.values():
            row["average_qty"] = row["quantity"] / row["purchases"]
            row["average_cost"] = row["cost"] / row["purchases"]
            suppliers.append(row)
        suppliers.sort(key=lambda row: (-row["purchases"], row["average_cost"]))
        suggested_qty = Decimal(product.reorder_qty or 0)
        if suggested_qty <= 0 and suppliers:
            suggested_qty = suppliers[0]["average_qty"]
        if suggested_qty <= 0:
            suggested_qty = max(Decimal("0"), level - stock)
        candidates.append({
            "product": product,
            "on_hand": stock,
            "reorder_level": level,
            "shortfall": max(Decimal("0"), level - stock),
            "suggested_qty": suggested_qty,
            "suppliers": suppliers,
        })
    return candidates


@login_required
def reorder_list(request):
    if request.method == "POST":
        selected = request.POST.getlist("products")
        supplier_ids = request.POST.getlist("suppliers")
        mode = request.POST.get("rfq_mode", "combined")
        if not selected or not supplier_ids:
            messages.error(request, "Select products and at least one supplier.")
            return redirect("accounts:reorder-list")

        candidates = {str(row["product"].id): row for row in _reorder_candidates(request)}
        selected_rows = [candidates[pid] for pid in selected if pid in candidates]
        suppliers = list(Supplier.objects.filter(pk__in=supplier_ids, active=True))
        if not selected_rows or not suppliers:
            messages.error(request, "The selected reorder items or suppliers are no longer available.")
            return redirect("accounts:reorder-list")

        with transaction.atomic():
            order = ConsolidatedOrder.objects.create(created_by=request.user, status="RFQ")
            lines = []
            for row in selected_rows:
                qty = Decimal(request.POST.get(f"qty_{row['product'].id}", row["suggested_qty"]) or 0)
                if qty <= 0:
                    continue
                lines.append(ConsolidatedOrderLine.objects.create(
                    consolidated_order=order,
                    product=row["product"],
                    branch=None,
                    total_qty=qty,
                ))
            if not lines:
                messages.error(request, "Enter a quantity for at least one selected product.")
                return redirect("accounts:reorder-list")

            if mode == "per_item":
                for line in lines:
                    for supplier in suppliers:
                        quotation = SupplierQuotation.objects.create(
                            consolidated_order=order,
                            supplier=supplier,
                            rfq_no=f"RFQ-{timezone.now():%Y%m%d}-{SupplierQuotation.objects.count()+1:04d}",
                            created_by=request.user,
                            status="DRAFT",
                        )
                        SupplierQuotationLine.objects.create(
                            quotation=quotation,
                            consolidated_line=line,
                            product=line.product,
                            qty=line.total_qty,
                        )
            else:
                for supplier in suppliers:
                    quotation = SupplierQuotation.objects.create(
                        consolidated_order=order,
                        supplier=supplier,
                        rfq_no=f"RFQ-{timezone.now():%Y%m%d}-{SupplierQuotation.objects.count()+1:04d}",
                        created_by=request.user,
                        status="DRAFT",
                    )
                    for line in lines:
                        SupplierQuotationLine.objects.create(
                            quotation=quotation,
                            consolidated_line=line,
                            product=line.product,
                            qty=line.total_qty,
                        )
        messages.success(request, "Reorder RFQ stage created successfully.")
        return redirect("accounts:rfqs")

    candidates = _reorder_candidates(request)
    suggested_supplier_ids = {
        supplier["supplier"].id
        for row in candidates
        for supplier in row["suppliers"]
    }
    suppliers = list(Supplier.objects.filter(active=True).order_by("name"))
    for supplier in suppliers:
        supplier.is_suggested = supplier.id in suggested_supplier_ids
    suppliers.sort(key=lambda supplier: (not supplier.is_suggested, supplier.name.lower()))
    return render(request, "accounts/procurement/reorder_list.html", {
        "candidates": candidates,
        "suppliers": suppliers,
    })

@login_required
def requisition_create(request):
    return requisition_form(request)

 
@login_required
def requisition_form(request, pk=None):

    requisition = None

    preview_number = (
        f"REQ-{timezone.now():%Y%m%d}-"
        f"{Requisition.objects.count() + 1:04d}"
    )

    if pk:
        requisition = get_object_or_404(
            Requisition,
            pk=pk
        )

    if request.method == "POST":
        required_date = request.POST.get("required_date")
        remarks = request.POST.get("remarks", "").strip()

        if not required_date:
            messages.error(request, "Required Date is required.")
            return render(
                request,
                "accounts/procurement/requisition_form.html",
                {
                    "requisition": requisition,
                    "products": Product.objects.filter(active=True).order_by("name"),
                    "preview_number": preview_number,
                },
            )

        if requisition is None:
            requisition = Requisition(
                requisition_no=f"REQ-{timezone.now():%Y%m%d}-{Requisition.objects.count() + 1:04d}",
                requested_by=request.user,
                status="DRAFT",
            )
            active_branch_id = request.session.get("active_branch_id")
            if active_branch_id:
                requisition.branch_id = active_branch_id

        requisition.required_date = required_date
        requisition.remarks = remarks
        requisition.save()

        requisition.lines.all().delete()
        for product_id, qty in zip(
            request.POST.getlist("product_id[]"),
            request.POST.getlist("qty_requested[]"),
        ):
            if product_id and qty:
                RequisitionLine.objects.create(
                    requisition=requisition,
                    product_id=product_id,
                    qty_requested=qty,
                )

        messages.success(request, "Requisition saved successfully.")
        return redirect("accounts:requisitions")

    return render(
        request,
        "accounts/procurement/requisition_form.html",
        {
            "requisition": requisition,
            "products": Product.objects.filter(active=True).order_by("name"),
            "preview_number": preview_number,
            "lines": requisition.lines.all() if requisition else [],
        },
    )
    
@login_required
def purchase_order_detail(request, pk):
    
    order = get_object_or_404(
        PurchaseHeader.objects
        .select_related("supplier")
        .prefetch_related(
            "lines",
            "lines__product",
        ),
        pk=pk
    )

    return render(
        request,
        "accounts/procurement/purchase_order_detail.html",
        {
            "order": order
        }
    )
    
    
@login_required
def purchase_order_pdf(request, pk):

    order = get_object_or_404(
        PurchaseHeader,
        pk=pk
    )

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; '
        f'filename="PO-{order.id}.pdf"'
    )

    doc = SimpleDocTemplate(
        response
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(

        Paragraph(
            f"Purchase Order {order.purchase_id}",
            styles["Title"]
        )

    )

    elements.append(Spacer(1, 20))

    data = [

        [
            "Product",
            "Qty",
            "Unit Cost",
            "Line Total"
        ]

    ]

    for line in order.lines.all():

        data.append([

            str(line.product),

            str(line.qty),

            str(line.buying_cost),

            str(line.line_total),

        ])

    data.append([

        "",
        "",
        "Grand Total",

        str(order.total)

    ])

    table = Table(data)

    table.setStyle(

        TableStyle([

            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),

            ("GRID", (0,0), (-1,-1), 1, colors.black),

            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),

        ])

    )

    elements.append(table)

    doc.build(elements)

    return response

@login_required
def requisition_delete(request, pk):

    requisition = get_object_or_404(
        Requisition,
        pk=pk
    )

    requisition.delete()

    messages.success(
        request,
        "Requisition deleted successfully."
    )

    return redirect(
        "accounts:requisitions"
    )
    

@login_required
def requisition_list(request):

    if request.method == "POST":

        selected = request.POST.getlist(
            "selected_requisitions"
        )

        action = request.POST.get(
            "action"
        )

        if not selected:

            messages.warning(
                request,
                "Please select at least one requisition."
            )

            return redirect(
                "accounts:requisitions"
            )

        if action == "submit":

            Requisition.objects.filter(
                id__in=selected,
                status="DRAFT"
            ).update(
                status="SUBMITTED"
            )

            messages.success(
                request,
                "Selected requisitions submitted."
            )

            return redirect(
                "accounts:requisitions"
            )

        elif action == "approve":

            Requisition.objects.filter(
                id__in=selected,
                status="SUBMITTED"
            ).update(
                status="APPROVED"
            )

            messages.success(
                request,
                "Selected requisitions approved."
            )

            return redirect(
                "accounts:requisitions"
            )

            
        elif action == "consolidate":

            print(
                "SELECTED IDS:",
                selected
            )

            return redirect(
                reverse(
                    "accounts:create-consolidated-order"
                )
                + "?"
                + urlencode(
                    {
                        "ids": ",".join(selected)
                    }
                )
            )

    requisitions = Requisition.objects.select_related(
        "branch",
        "requested_by"
    )

    q = request.GET.get("q")
    status = request.GET.get("status")

    if q:

        requisitions = requisitions.filter(

            Q(requisition_no__icontains=q) |
            Q(branch__name__icontains=q) |
            Q(requested_by__username__icontains=q) |
            Q(remarks__icontains=q)

        )

    if status:

        requisitions = requisitions.filter(
            status=status
        )

    requisitions = requisitions.order_by(
        "-created_at"
    )

    submitted_count = Requisition.objects.filter(
        status="SUBMITTED"
    ).count()

    approved_count = Requisition.objects.filter(
        status="APPROVED"
    ).count()

    pending_count = Requisition.objects.filter(
        status="DRAFT"
    ).count()


    return render(
        request,
        "accounts/procurement/requisition_list.html",
        {
            "requisitions": requisitions,
            "q": q,
            "status": status,
            "submitted_count": submitted_count,
            "approved_count": approved_count,
            "pending_count": pending_count,
        }
    )


@login_required
def consolidated_order_list(request):

    orders = (
        ConsolidatedOrder.objects
        .select_related("created_by")
        .prefetch_related("lines")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/procurement/consolidated_orders.html",
        {
            "orders": orders
        }
    )
    
    
@login_required
def create_consolidated_order(request):

    ids = request.GET.get("ids", "")
    print("RAW IDS:", ids)

    id_list = [
        x.strip()
        for x in ids.split(",")
        if x.strip()
    ]

    print("ID LIST:", id_list)

    approved = Requisition.objects.filter(
        id__in=id_list,
        status="APPROVED"
    )

    if not approved.exists():
        messages.warning(
            request,
            "No approved requisitions selected."
        )
        return redirect(
            "accounts:requisitions"
        )

    totals = {}

    for req in approved:

        for line in req.lines.filter(
            approved=True,
            consolidated=False
        ):

            # One consolidated line per product; branch demand is retained
            # in ConsolidatedAllocation rows below.
            key = line.product_id

            if key not in totals:
                totals[key] = {
                    "product": line.product,
                    "qty": 0,
                }

            totals[key]["qty"] += line.qty_approved

    if not totals:
        messages.warning(
            request,
            "No approved requisition items available for consolidation."
        )
        return redirect(
            "accounts:requisitions"
        )

    co = ConsolidatedOrder.objects.create(
        created_by=request.user,
        status="DRAFT"
    )

    # Create ConsolidatedOrderLine ONCE and build line_map
    line_map = {}

    for item in totals.values():

        coline = ConsolidatedOrderLine.objects.create(
            consolidated_order=co,
            product=item["product"],
            branch=None,
            total_qty=item["qty"],
        )

        line_map[item["product"].id] = coline

    # Create allocations
    for req in approved:

        for rline in req.lines.filter(
            approved=True,
            consolidated=False
        ):

            key = rline.product_id

            coline = line_map[key]

            ConsolidatedAllocation.objects.create(
                consolidated_line=coline,
                requisition=req,
                requisition_line=rline,
                allocated_qty=rline.qty_approved
            )

    # Mark requisition lines as consolidated
    for req in approved:

        pending = req.lines.filter(
            approved=True,
            consolidated=False
        )
        pending.update(consolidated=True)

        remaining = req.lines.filter(
            approved=True,
            consolidated=False
        ).exists()

        if not remaining:
            req.status = "CONSOLIDATED"
            req.save()

    messages.success(
        request,
        f"Consolidated Order {co.id} created successfully."
    )

    return redirect(
        "accounts:consolidated-orders"
    )


@login_required
def consolidated_order_detail(request, pk):

    order = get_object_or_404(
        ConsolidatedOrder.objects
        .select_related(
            "created_by",
            "approved_by",
        )
        .prefetch_related(
            "lines",
            "lines__product",
            "lines__allocations__requisition__branch",
        ),
        pk=pk
    )

    return render(
        request,
        "accounts/procurement/consolidated_order_detail.html",
        {
            "order": order
        }
    )
    
@login_required
def consolidated_order_approve(request,pk):

    order = get_object_or_404(
        ConsolidatedOrder,
        pk=pk
    )

    order.status = "APPROVED"

    order.approved_by = request.user

    order.approved_at = timezone.now()

    order.save()

    messages.success(
        request,
        f"Consolidated Order CO-{order.id} approved."
    )

    return redirect(
        "accounts:consolidated-orders"
    )
    


from decimal import Decimal
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import (
    get_object_or_404,
    redirect,
)
from django.contrib.auth.decorators import login_required

from accounts.models.procurement import (
    SupplierQuotation,
)

from accounts.models.purchase import (
    PurchaseHeader,
    PurchaseLine,
)


@login_required
def generate_purchase_order(request, pk):

    quotation = get_object_or_404(
        SupplierQuotation,
        pk=pk
    )

    awarded_lines = quotation.lines.filter(awarded=True)

    if not awarded_lines.exists():
        messages.warning(
            request,
            "Only awarded quotations can generate a Purchase Order."
        )

        return redirect(
            "accounts:quotation-comparison",
            quotation.consolidated_order.id
        )

    existing_po = PurchaseHeader.objects.filter(
        supplier=quotation.supplier,
        reference=quotation.rfq_no
    ).first()

    if existing_po:

        messages.warning(
            request,
            (
                f"Purchase Order already exists "
                f"for RFQ {quotation.rfq_no}."
            )
        )

        return redirect(
            "accounts:purchase-orders"
        )

    branch = Branch.objects.filter(
        pk=request.session.get("active_branch_id")
    ).first()
    if not branch:
        messages.error(
            request,
            "Select an active receiving branch before generating a purchase order."
        )
        return redirect(
            "accounts:quotation-comparison",
            quotation.consolidated_order.id
        )

    po = PurchaseHeader.objects.create(

        branch=branch,

        created_by=request.user,

        supplier=quotation.supplier,

        reference=quotation.rfq_no,

        purchase_date=timezone.now().date(),

        status="DRAFT",

        total=Decimal("0.00")
    )

    total = Decimal("0.00")

    for line in awarded_lines:

        PurchaseLine.objects.create(

            header=po,

            consolidated_line=line.consolidated_line,

            product=line.product,

            qty=line.qty,

            buying_cost=line.unit_price,

            line_total=line.total_amount
        )

        total += line.total_amount

    po.total = total

    po.save()

    quotation.status = "ORDERED"

    quotation.save()

    order = quotation.consolidated_order
    remaining_awards = SupplierQuotationLine.objects.filter(
        quotation__consolidated_order=order,
        awarded=True,
    ).exclude(
        quotation__status="ORDERED",
    ).exists()

    if not remaining_awards:
        order.status = "ORDERED"
        order.save()

    messages.success(
        request,
        (
            f"Purchase Order "
            f"{po.purchase_id} "
            f"generated successfully."
        )
    )

    return redirect(
        "accounts:purchase-orders"
    )

    
    
@login_required
def create_rfq(request, pk):

    order = get_object_or_404(
        ConsolidatedOrder,
        pk=pk
    )

    if order.status != "APPROVED":

        messages.warning(
            request,
            "Only approved consolidated orders can be sent for RFQ."
        )

        return redirect(
            "accounts:consolidated-orders"
        )

    if request.method == "POST":
            
        supplier_ids = request.POST.getlist(
            "suppliers"
        )

        for supplier_id in supplier_ids:

            rfq = SupplierQuotation.objects.create(

                rfq_no=(
                    f"RFQ-{timezone.now():%Y%m%d}-"
                    f"{SupplierQuotation.objects.count()+1:04d}"
                ),

                consolidated_order=order,

                supplier_id=supplier_id,

                created_by=request.user,

                status="DRAFT"
            )

            for line in order.lines.all():

                SupplierQuotationLine.objects.create(

                    quotation=rfq,

                    consolidated_line=line,

                    product=line.product,

                    qty=line.total_qty

                )

        order.status = "RFQ"

        order.save()

        messages.success(
            request,
            "RFQ created successfully."
        )

        return redirect(
            "accounts:rfqs"
        )

    suppliers = Supplier.objects.all()

    return render(
        request,
        "accounts/procurement/create_rfq.html",
        {
            "order": order,
            "suppliers": suppliers,
        }
    )
    

@login_required
def quotation_comparison(request, pk):

    order = get_object_or_404(
        ConsolidatedOrder.objects.select_related(
            "created_by",
            "approved_by"
        ),
        pk=pk
    )

    quotations = (
        SupplierQuotation.objects
        .filter(consolidated_order=order)
        .select_related("supplier")
        .prefetch_related(
            "lines",
            "lines__product"
        )
    )

    comparison = []
    cheapest_by_product = {}

    for quotation in quotations:
        for line in quotation.lines.all():
            if not line.unit_price or line.unit_price <= 0:
                continue
            current = cheapest_by_product.get(line.product_id)
            if current is None or (
                line.unit_price,
                quotation.id,
            ) < (
                current.unit_price,
                current.quotation_id,
            ):
                cheapest_by_product[line.product_id] = line

        quoted_lines = [
            line for line in quotation.lines.all()
            if line.unit_price and line.unit_price > 0
        ]
        total_value = sum(
            (line.total_amount or 0 for line in quoted_lines),
            Decimal("0"),
        )

        comparison.append({
            "quotation": quotation,
            "total": total_value,
            "quoted_count": len(quoted_lines),
            "awarded_count": sum(
                1 for line in quoted_lines if line.awarded
            ),
        })

    return render(
        request,
        "accounts/procurement/quotation_comparison.html",
        {
            "order": order,
            "quotations": quotations,
            "comparison": comparison,
            "lowest_line_ids": {
                line.id for line in cheapest_by_product.values()
            },
            "recommended": None,
        }
    )
    

    
@login_required
def award_supplier(request, pk):

    quotation = get_object_or_404(
        SupplierQuotation,
        pk=pk
    )

    order = quotation.consolidated_order

    quotations = list(
        SupplierQuotation.objects
        .filter(consolidated_order=order)
        .prefetch_related("lines")
    )

    cheapest_by_product = {}
    for candidate in quotations:
        for line in candidate.lines.all():
            if not line.unit_price or line.unit_price <= 0:
                continue
            current = cheapest_by_product.get(line.product_id)
            if current is None or (
                line.unit_price,
                candidate.id,
            ) < (
                current.unit_price,
                current.quotation_id,
            ):
                cheapest_by_product[line.product_id] = line

    with transaction.atomic():
        SupplierQuotationLine.objects.filter(
            quotation__consolidated_order=order
        ).update(awarded=False)

        winner_ids = [line.id for line in cheapest_by_product.values()]
        SupplierQuotationLine.objects.filter(
            id__in=winner_ids
        ).update(awarded=True)

        for candidate in quotations:
            has_winner = any(
                line.quotation_id == candidate.id
                and line.id in winner_ids
                for line in candidate.lines.all()
            )
            candidate.status = "AWARDED" if has_winner else "NOT_AWARDED"
            candidate.awarded = has_winner
            candidate.awarded_by = request.user if has_winner else None
            candidate.awarded_at = timezone.now() if has_winner else None
            candidate.save(update_fields=[
                "status", "awarded", "awarded_by", "awarded_at"
            ])

    order.status = "AWARDED"
    order.save()

    messages.success(
        request,
        f"{len(winner_ids)} item(s) awarded to the lowest quoted supplier(s)."
    )

    return redirect(
        "accounts:quotation-comparison",
        order.id
    )


@login_required
def award_quotation_line(request, pk):

    line = get_object_or_404(
        SupplierQuotationLine.objects.select_related(
            "quotation__consolidated_order"
        ),
        pk=pk
    )

    if not line.unit_price or line.unit_price <= 0:
        messages.warning(
            request,
            "Only quoted items can be awarded."
        )
        return redirect(
            "accounts:quotation-comparison",
            line.quotation.consolidated_order_id
        )

    order = line.quotation.consolidated_order

    with transaction.atomic():
        SupplierQuotationLine.objects.filter(
            quotation__consolidated_order=order,
            product_id=line.product_id,
        ).update(awarded=False)

        line.awarded = True
        line.save(update_fields=["awarded"])

        quotations = list(
            SupplierQuotation.objects
            .filter(consolidated_order=order)
            .prefetch_related("lines")
        )

        for candidate in quotations:
            has_awarded_line = candidate.lines.filter(
                awarded=True
            ).exists()
            candidate.status = "AWARDED" if has_awarded_line else "NOT_AWARDED"
            candidate.awarded = has_awarded_line
            candidate.awarded_by = request.user if has_awarded_line else None
            candidate.awarded_at = timezone.now() if has_awarded_line else None
            candidate.save(update_fields=[
                "status", "awarded", "awarded_by", "awarded_at"
            ])

        order.status = "AWARDED"
        order.save(update_fields=["status"])

    messages.success(
        request,
        f"{line.product} awarded to {line.quotation.supplier}."
    )

    return redirect(
        "accounts:quotation-comparison",
        order.id
    )
    
@login_required
def quotation_entry(request, pk):

    quotation = get_object_or_404(
        SupplierQuotation,
        pk=pk
    )

    if request.method == "POST":

        for line in quotation.lines.all():

            unit_price = request.POST.get(
                f"price_{line.id}",
                0
            )


            try:

                unit_price = Decimal(
                    str(unit_price)
                )

            except (TypeError, ValueError):

                unit_price = Decimal("0")

            
            line.unit_price = unit_price

            line.total_amount = (
                line.qty * unit_price
            )

            line.save()

        quotation.status = "RECEIVED"

        quotation.save()

        messages.success(
            request,
            "Supplier quotation captured successfully."
        )

        return redirect(
            "accounts:rfqs"
        )

    return render(
        request,
        "accounts/procurement/quotation_entry.html",
        {
            "quotation": quotation
        }
    )

@login_required
def requisition_approve(request, pk):

    requisition = get_object_or_404(
        Requisition,
        pk=pk
    )

    if request.method == "POST":

        selected_lines = request.POST.getlist(
            "approved_lines"
        )

        for line in requisition.lines.all():

            approved_qty = request.POST.get(
                f"qty_{line.id}",
                0
            )

            if str(line.id) in selected_lines:

                line.approved = True
                line.qty_approved = approved_qty
                line.approved_by = request.user

            else:

                line.approved = False
                line.qty_approved = 0

            line.save()

        requisition.status = "APPROVED"
        requisition.save()

        messages.success(
            request,
            "Requisition approved successfully."
        )

        return redirect(
            "accounts:requisitions"
        )

    return render(
        request,
        "accounts/procurement/requisition_approval.html",
        {
            "requisition": requisition
        }
    )

@login_required
def rfq_list(request):

    rfqs = (
        SupplierQuotation.objects
        .select_related(
            "supplier",
            "consolidated_order"
        )
        .order_by("-id")
    )

    return render(
        request,
        "accounts/procurement/rfq_list.html",
        {
            "rfqs": rfqs
        }
    )


@login_required
def purchase_order_list(request):

    from accounts.models.purchase import PurchaseHeader

    orders = (
        PurchaseHeader.objects
        .select_related("supplier")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/procurement/purchase_orders.html",
        {
            "orders": orders
        }
    )


@login_required
def goods_receipt_list(request):

    receipts = (
        GoodsReceipt.objects
        .select_related(
            "supplier",
            "branch"
        )
        .order_by("-id")
    )

    return render(
        request,
        "accounts/procurement/goods_receipts.html",
        {
            "receipts": receipts
        }
    )

@login_required
def create_grn(request, pk):

    order = get_object_or_404(
        PurchaseHeader.objects.select_related(
            "supplier",
            "branch",
        ).prefetch_related(
            "lines__product",
            "lines__consolidated_line__allocations__requisition__branch",
        ),
        pk=pk
    )

    if request.method == "POST":

        receipt_mode = request.POST.get(
            "receipt_mode",
            "CONSOLIDATED_BRANCH",
        )
        destination_branch = get_object_or_404(
            Branch,
            pk=request.POST.get("destination_branch") or order.branch_id,
        )
        prepared = []

        for line in order.lines.all():
            try:
                received_qty = Decimal(
                    request.POST.get(f"received_{line.id}", "0") or "0"
                )
            except (TypeError, ValueError):
                received_qty = Decimal("0")

            if received_qty <= 0:
                continue

            already_received = (
                GoodsReceiptLine.objects.filter(
                    po_line=line
                ).aggregate(total=Sum("received_qty"))["total"]
                or Decimal("0")
            )
            remaining_qty = line.qty - already_received
            if received_qty > remaining_qty:
                messages.error(
                    request,
                    f"{line.product} only has {remaining_qty} remaining to receive."
                )
                return redirect("accounts:create-grn", pk=order.id)

            batch_no = request.POST.get(f"batch_{line.id}", "").strip()
            expiry_date = request.POST.get(f"expiry_{line.id}") or None
            if not batch_no:
                messages.error(request, f"Batch number is required for {line.product}.")
                return redirect("accounts:create-grn", pk=order.id)
            if expiry_date and date.fromisoformat(expiry_date) <= timezone.now().date():
                messages.error(request, f"{line.product} has an expired batch.")
                return redirect("accounts:create-grn", pk=order.id)

            targets = []
            if line.consolidated_line_id:
                allocated_total = Decimal("0")
                for allocation in line.consolidated_line.allocations.all():
                    if (
                        receipt_mode == "ORIGINAL_BRANCHES"
                        and allocation.requisition.branch_id != destination_branch.id
                    ):
                        continue
                    allocation_received = (
                        GoodsReceiptAllocation.objects.filter(
                            allocation=allocation
                        ).aggregate(total=Sum("qty"))["total"]
                        or Decimal("0")
                    )
                    allocation_remaining = (
                        allocation.allocated_qty - allocation_received
                    )
                    if receipt_mode == "ORIGINAL_BRANCHES":
                        try:
                            target_qty = Decimal(
                                request.POST.get(
                                    f"allocation_{allocation.id}",
                                    "0",
                                ) or "0"
                            )
                        except (TypeError, ValueError):
                            target_qty = Decimal("0")
                        target_branch = allocation.requisition.branch
                    else:
                        target_qty = min(
                            allocation_remaining,
                            received_qty - allocated_total,
                        )
                        target_branch = destination_branch

                    if target_qty < 0 or target_qty > allocation_remaining:
                        messages.error(
                            request,
                            f"Invalid receipt quantity for {allocation.requisition.branch} "
                            f"({line.product}). Remaining: {allocation_remaining}."
                        )
                        return redirect("accounts:create-grn", pk=order.id)
                    if target_qty:
                        targets.append((allocation, target_qty, target_branch))
                        allocated_total += target_qty

                if allocated_total != received_qty:
                    messages.error(
                        request,
                        f"Branch allocations for {line.product} must equal {received_qty}."
                    )
                    return redirect("accounts:create-grn", pk=order.id)
            else:
                targets.append((None, received_qty, destination_branch))

            prepared.append((line, received_qty, batch_no, expiry_date, targets))

        if not prepared:
            messages.warning(request, "Enter at least one quantity to receive.")
            return redirect("accounts:create-grn", pk=order.id)

        with transaction.atomic():

            grn = GoodsReceipt.objects.create(

                po=order,

                branch=destination_branch,

                supplier=order.supplier,

                received_by=request.user,

                receipt_mode=receipt_mode,

                status="RECEIVED"
            )

            for line, received_qty, batch_no, expiry_date, targets in prepared:
                receipt_line = GoodsReceiptLine.objects.create(

                    receipt=grn,
                    po_line=line,
                    product=line.product,
                    ordered_qty=line.qty,
                    received_qty=received_qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date
                )

                for allocation, target_qty, target_branch in targets:
                    batch, _created = StockBatch.objects.get_or_create(
                        product=line.product,
                        branch=target_branch,
                        batch_no=batch_no,
                        expiry_date=expiry_date,
                        defaults={
                            "qty_on_hand": Decimal("0.0000"),
                            "buying_cost": line.buying_cost,
                        }
                    )
                    StockBatch.objects.filter(pk=batch.pk).update(
                        qty_on_hand=F("qty_on_hand") + target_qty,
                        buying_cost=line.buying_cost,
                    )
                    StockLedger.objects.create(
                        product=line.product,
                        branch=target_branch,
                        batch=batch,
                        qty_change=target_qty,
                        unit_cost=line.buying_cost,
                        reason=StockLedger.IN,
                        reference=f"GRN-{str(grn.grn_no)[:8]}",
                    )
                    if allocation:
                        GoodsReceiptAllocation.objects.create(
                            receipt_line=receipt_line,
                            allocation=allocation,
                            branch=target_branch,
                            qty=target_qty,
                        )
                        ConsolidatedAllocation.objects.filter(
                            pk=allocation.pk
                        ).update(
                            fulfilled_qty=F("fulfilled_qty") + target_qty
                        )

            fully_received = True

            for po_line in order.lines.all():

                total_received = (
                    GoodsReceiptLine.objects.filter(
                        po_line=po_line
                    ).aggregate(
                        total=Sum("received_qty")
                    )["total"]
                    or Decimal("0")
                )

                if total_received < po_line.qty:

                    fully_received = False

                    break

            if fully_received:

                order.status = "RECEIVED"

            else:

                order.status = "PART_RECEIVED"

            order.save()

            messages.success(

                request,

                (
                    f"GRN "
                    f"{str(grn.grn_no)[:8]} "
                    f"posted successfully."
                )
            )

            return redirect(
                "accounts:goods-receipts"
            )

    for line in order.lines.all():
        received_to_date = (
            GoodsReceiptLine.objects.filter(
                po_line=line
            ).aggregate(total=Sum("received_qty"))["total"]
            or Decimal("0")
        )
        line.received_to_date = received_to_date
        line.remaining_qty = max(Decimal("0"), line.qty - received_to_date)

        if line.consolidated_line_id:
            for allocation in line.consolidated_line.allocations.all():
                allocation.received_to_date = (
                    GoodsReceiptAllocation.objects.filter(
                        allocation=allocation
                    ).aggregate(total=Sum("qty"))["total"]
                    or Decimal("0")
                )
                allocation.remaining_qty = max(
                    Decimal("0"),
                    allocation.allocated_qty - allocation.received_to_date,
                )

    return render(
        request,
        "accounts/procurement/grn_form.html",
        {
            "order": order,
            "branches": Branch.objects.all().order_by("name"),
            "receiving_branch_id": request.session.get("active_branch_id") or order.branch_id,
        }
    )
    
@login_required
def goods_receipt_detail(request, pk):

    receipt = get_object_or_404(
        GoodsReceipt.objects
        .select_related(
            "supplier",
            "branch",
            "received_by",
            "po"
        )
        .prefetch_related(
            "lines",
            "lines__product"
        ),
        pk=pk
    )


    return render(
        request,
        "accounts/procurement/goods_receipt_detail.html",
        {
            "receipt": receipt
        }
    )

@login_required
def supplier_invoice_list(request):

    invoices = (
        SupplierInvoice.objects
        .select_related("supplier")
        .order_by("-invoice_date")
    )

    return render(
        request,
        "accounts/procurement/supplier_invoices.html",
        {
            "invoices": invoices
        }
    )
    
    
@login_required
def create_supplier_invoice(request, pk):

    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    available_lines = GoodsReceiptLine.objects.select_related(
        "product", "po_line", "receipt"
    ).filter(
        receipt__po=receipt.po,
        received_qty__gt=F("invoiced_qty"),
    )
    if not available_lines.exists():
        messages.warning(
            request,
            "This purchase order has no uninvoiced received quantity remaining."
        )
        return redirect("accounts:supplier-invoices")

    with transaction.atomic():
        invoice = SupplierInvoice.objects.create(
            invoice_no=(
                f"INV-{timezone.now():%Y%m%d}-"
                f"{SupplierInvoice.objects.count()+1:04d}"
            ),
            supplier=receipt.supplier,
            purchase_order=receipt.po,
            grn=receipt,
            invoice_date=timezone.now().date(),
            created_by=request.user,
            status="DRAFT",
        )

        total = Decimal("0.00")
        for line in available_lines.select_for_update():
            qty = line.received_qty - line.invoiced_qty
            unit_cost = line.po_line.buying_cost
            line_total = qty * unit_cost
            SupplierInvoiceLine.objects.create(
                invoice=invoice,
                receipt_line=line,
                product=line.product,
                qty=qty,
                unit_cost=unit_cost,
                line_total=line_total,
            )
            GoodsReceiptLine.objects.filter(pk=line.pk).update(
                invoiced_qty=F("invoiced_qty") + qty
            )
            total += line_total

        invoice.total_amount = total
        invoice.save(update_fields=["total_amount"])

        fully_received = True
        fully_invoiced = True
        for po_line in receipt.po.lines.all():
            totals = GoodsReceiptLine.objects.filter(
                po_line=po_line
            ).aggregate(
                received=Sum("received_qty"),
                invoiced=Sum("invoiced_qty"),
            )
            received = totals["received"] or Decimal("0")
            invoiced = totals["invoiced"] or Decimal("0")
            if received < po_line.qty:
                fully_received = False
            if invoiced < received:
                fully_invoiced = False
        receipt.po.status = "INVOICED" if fully_received and fully_invoiced else (
            "RECEIVED" if fully_received else "PART_RECEIVED"
        )
        receipt.po.save(update_fields=["status"])

    messages.success(
        request,
        "Supplier Invoice created for all received, uninvoiced goods on this purchase order."
    )

    return redirect(
        "accounts:supplier-invoices"
    )
    
@login_required
def supplier_invoice_detail(request, pk):
    
    invoice = get_object_or_404(
        SupplierInvoice.objects
        .select_related(
            "supplier",
            "purchase_order",
            "grn",
            "created_by"
        )
        .prefetch_related(
            "lines",
            "lines__product",
            "lines__receipt_line__receipt"
        ),
        pk=pk
    )

    return render(
        request,
        "accounts/procurement/supplier_invoice_detail.html",
        {
            "invoice": invoice,
            "invoice_receipt_count": invoice.lines.values("receipt_line__receipt_id").distinct().count(),
        }
    )
    
@login_required
def supplier_invoice_pdf(request, pk):

    invoice = get_object_or_404(
        SupplierInvoice.objects.prefetch_related(
            "lines"
        ),
        pk=pk
    )

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; '
        f'filename="{invoice.invoice_no}.pdf"'
    )

    doc = SimpleDocTemplate(
        response
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(

        Paragraph(
            f"Supplier Invoice {invoice.invoice_no}",
            styles["Title"]
        )

    )

    elements.append(Spacer(1, 15))

    elements.append(

        Paragraph(
            f"Supplier: {invoice.supplier}",
            styles["Normal"]
        )

    )

    elements.append(

        Paragraph(
            f"Invoice Date: {invoice.invoice_date}",
            styles["Normal"]
        )

    )

    elements.append(Spacer(1, 15))

    data = [[

        "Product",
        "Qty",
        "Cost Price",
        "Trade Price",
        "Total"

    ]]

    for line in invoice.lines.all():

        data.append([

            str(line.product),

            str(line.qty),

            str(line.unit_cost),

            str(line.trade_price),

            str(line.line_total)

        ])

    data.append([

        "",
        "",
        "",
        "Grand Total",

        str(invoice.total_amount)

    ])

    table = Table(data)

    table.setStyle(

        TableStyle([

            ("BACKGROUND",
             (0, 0),
             (-1, 0),
             colors.lightgrey),

            ("GRID",
             (0, 0),
             (-1, -1),
             1,
             colors.black),

            ("FONTNAME",
             (0, 0),
             (-1, 0),
             "Helvetica-Bold"),

        ])
    )

    elements.append(table)

    doc.build(elements)

    return response

    