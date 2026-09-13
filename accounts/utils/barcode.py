import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.http import HttpResponse

def generate_barcode_image(code, barcode_type="code128"):
    """
    Supported types: code128, ean13, ean8, upc
    """
    BARCODE = barcode.get_barcode_class(barcode_type)
    buffer = BytesIO()
    BARCODE(code, writer=ImageWriter()).write(buffer)

    return buffer.getvalue()