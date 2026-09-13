from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from io import BytesIO
from django.http import HttpResponse
from django.utils.timezone import now

def generate_transfer_pdf(transfer):
    """
    transfer = {
        'product': 'Paracetamol',
        'sku': 'SKU-000004',
        'from': 'Kisumu',
        'to': 'Nairobi',
        'qty': 12
    }
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50

    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, y, "Internal Stock Transfer Work Order")

    y -= 40
    c.setFont("Helvetica", 12)
    c.drawString(40, y, f"Date: {now().strftime('%Y-%m-%d %H:%M')}")

    y -= 20
    c.drawString(40, y, f"From Branch: {transfer['from']}")
    y -= 20
    c.drawString(40, y, f"To Branch: {transfer['to']}")

    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "ITEM DETAILS")

    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(40, y, f"Product: {transfer['product']}")
    y -= 20
    c.drawString(40, y, f"SKU: {transfer['sku']}")
    y -= 20
    c.drawString(40, y, f"Quantity to Transfer: {transfer['qty']} units")

    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "SIGNATURES")

    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(40, y, "Issued By: _______________________")

    y -= 40
    c.drawString(40, y, "Driver / Courier: _______________________")

    y -= 40
    c.drawString(40, y, "Received By: _______________________")

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()
    return pdf