import os
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode
from reportlab.lib.colors import HexColor
from .models import Certificate

def generate_certificate_pdf(certificate_id):
    """
    Generates a PDF for a certificate using its template and registration data.
    """
    cert = Certificate.objects.select_related(
        'registration__user', 
        'registration__event', 
        'template'
    ).get(id=certificate_id)
    
    template = cert.template
    user = cert.registration.user
    event = cert.registration.event
    
    # Create a file-like buffer to receive PDF data
    buffer = BytesIO()
    
    # Create the PDF object, using the response object as its "file."
    # Most certificates are landscape A4
    p = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # 1. Draw Background Image
    if template.background_image:
        bg_path = template.background_image.path
        p.drawImage(bg_path, 0, 0, width=width, height=height)
    
    # 2. Draw Dynamic Fields based on layout_config
    # Expected config format: { "fields": [{"type": "name", "x": 100, "y": 200, "font": "Helvetica-Bold", "size": 36, "color": "#000000"}, ...] }
    layout = template.layout_config.get('fields', [])
    
    for field in layout:
        field_type = field.get('type')
        x = field.get('x', 0) * (width / 1000) # Assuming 1000x1000 coordinate system
        y = field.get('y', 0) * (height / 1000)
        font = field.get('font', 'Helvetica')
        size = field.get('size', 12) * (width / 1000) # Proportional scaling
        
        text = ""
        if field_type == 'participant_name':
            text = user.get_full_name()
        elif field_type == 'event_name':
            text = event.title
        elif field_type == 'date':
            text = cert.issue_date.strftime('%B %d, %Y')
        elif field_type == 'cert_id':
            text = cert.certificate_id
        elif field_type == 'qr_code':
            # QR Code is handled as an image later in section 3
            continue
        elif field_type == 'custom':
            text = field.get('text', '')
            
        if text:
            color_hex = field.get('color', '#000000')
            p.setFillColor(HexColor(color_hex))
            
            p.setFont(font, size)
            # Center alignment logic if needed
            if field.get('align') == 'center':
                p.drawCentredString(x, y, text)
            else:
                p.drawString(x, y, text)
                
    # 3. Draw Verification QR Code
    qr_url = f"{settings.SITE_URL}/verify/{cert.certificate_id}/"
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    
    # Search for QR position in layout
    qr_field = next((f for f in layout if f.get('type') == 'qr_code'), None)
    if qr_field:
        qr_x = qr_field.get('x', 0) * (width / 1000)
        qr_y = qr_field.get('y', 0) * (height / 1000)
        # Use direct scaling from designer without multipliers for perfect parity
        qr_size = qr_field.get('size', 80) * (width / 1000)
    else:
        # Default fallback (bottom left)
        qr_x = 20 * mm
        qr_y = 20 * mm
        qr_size = 30 * mm
    
    p.drawImage(ImageReader(qr_buffer), qr_x, qr_y, width=qr_size, height=qr_size)
    
    # 4. Finalize PDF
    p.showPage()
    p.save()
    
    # 5. Save to model
    pdf_filename = f"cert_{cert.certificate_id}.pdf"
    cert.pdf_file.save(pdf_filename, ContentFile(buffer.getvalue()), save=False)
    
    # Save verification QR separately if needed for preview
    qr_buffer.seek(0)
    cert.verification_qr.save(f"qr_{cert.certificate_id}.png", ContentFile(qr_buffer.getvalue()), save=False)
    
    cert.status = 'completed'
    cert.save()
    return cert.pdf_file.url
