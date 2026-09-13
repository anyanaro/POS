from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponse
from openpyxl import Workbook

from accounts.utils.product_import import import_products


@login_required
def product_import_page(request):
    result = None
    if request.method == "POST":
        upload = request.FILES.get("file")
        dry_run = request.POST.get("dry_run") == "1"
        if not upload or not upload.name.lower().endswith(".xlsx"):
            messages.error(request, "Upload an .xlsx workbook.")
        else:
            result = import_products(upload, commit=not dry_run)
            if result["errors"]:
                messages.error(request, "Import validation found errors. No products were created.")
            elif dry_run:
                messages.success(request, f"Dry run passed for {len(result['preview'])} products.")
            else:
                messages.success(request, f"Imported {result['created']} products successfully.")
    return render(request, "accounts/integrations/product_import.html", {"result": result})


@login_required
def product_import_template(request):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"
    sheet.append([
        "bc_number",
        "name",
        "barcode",
        "buying_cost",
        "unit_price",
        "reorder_level",
        "reorder_qty",
        "supplier",
    ])
    sheet.append([
        "BC-ITEM-0001",
        "Example Product",
        "",
        0,
        0,
        0,
        0,
        "Supplier name or supplier ID",
    ])

    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Column", "Required", "Description"])
    instructions.append(["bc_number", "Yes", "Business Central item number. Must be unique."])
    instructions.append(["name", "Yes", "Product name."])
    instructions.append(["unit_price", "Yes", "Selling price; must be numeric and non-negative."])
    instructions.append(["sku", "Generated", "Generated automatically in sequence when the import is applied."])
    instructions.append(["barcode", "No", "Product barcode."])
    instructions.append(["buying_cost", "No", "Default buying cost."])
    instructions.append(["reorder_level", "No", "Stock level that triggers replenishment."])
    instructions.append(["reorder_qty", "No", "Suggested replenishment quantity."])
    instructions.append(["supplier", "No", "Exact supplier name or numeric supplier ID."])
    instructions.append(["", "", "Delete the example row before importing real products."])

    for sheet in workbook.worksheets:
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 24
        sheet.freeze_panes = "A2"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="product-import-template.xlsx"'
    workbook.save(response)
    return response
