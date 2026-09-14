import os
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode
from PIL import Image
import fitz
from reportlab.lib.colors import HexColor
from .models import Certificate

def generate_certificate_pdf(certificate_id):
    """
    Generates a high-fidelity PDF for a certificate using its template and registration data.
    Ensures crisp rendering of background image, typography, and QR code.
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
    # Detect orientation from background image
    pagesize = landscape(A4)
    if template.background_image:
        try:
            bg_path = template.background_image.path
            with Image.open(bg_path) as img:
                img_width, img_height = img.size
                if img_height > img_width:
                    pagesize = A4
        except Exception:
            pass
            
    p = canvas.Canvas(buffer, pagesize=pagesize)
    width, height = pagesize
    
    # 1. Draw Background Image with high-fidelity settings
    if template.background_image:
        bg_path = template.background_image.path
        # mask='auto' prevents jagged chroma keying and preserves smooth gradients
        p.drawImage(bg_path, 0, 0, width=width, height=height, mask='auto', preserveAspectRatio=False)
    
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
            # Look up dynamic custom fields in registration.custom_data.
            # Use the field's configured text as the key to look up (e.g., if placeholder is "Position", we look up custom_data['Position']).
            field_name = field.get('text', '')
            reg_custom_data = cert.registration.custom_data or {}
            
            # Look up key case-insensitively
            text = None
            if field_name:
                text = reg_custom_data.get(field_name) or reg_custom_data.get(field_name.lower()) or reg_custom_data.get(field_name.title())
            
            # General fallbacks for common custom fields like Position/Role
            if not text:
                text = reg_custom_data.get('Position') or reg_custom_data.get('position') or reg_custom_data.get('Role') or reg_custom_data.get('role')
                
            # If not found in custom_data, fall back to the static placeholder text
            if not text:
                text = field_name
            
        if text:
            color_hex = field.get('color', '#000000')
            p.setFillColor(HexColor(color_hex))
            
            # Auto-scaling logic: Ensure text fits within a safe horizontal margin
            # Default safe width is 80% of page width
            max_allowed_width = width * 0.8
            current_text_width = p.stringWidth(text, font, size)
            
            scaled_size = size
            while current_text_width > max_allowed_width and scaled_size > 8:
                scaled_size -= 1
                current_text_width = p.stringWidth(text, font, scaled_size)
            
            p.setFont(font, scaled_size)
            
            # Center alignment logic if needed
            if field.get('align') == 'center':
                p.drawCentredString(x, y, text)
            else:
                p.drawString(x, y, text)
                
    # 3. Draw Verification QR Code ONLY if it exists in the layout
    qr_field = next((f for f in layout if f.get('type') == 'qr_code'), None)
    
    if qr_field:
        qr_url = f"{settings.SITE_URL}/verify/{cert.certificate_id}/"
        # Super-sampled box_size=10 for ultra-sharp scanning at any resolution
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

        qr_x = qr_field.get('x', 0) * (width / 1000)
        qr_y = qr_field.get('y', 0) * (height / 1000)
        # Use direct scaling from designer without multipliers for perfect parity
        qr_size = qr_field.get('size', 80) * (width / 1000)
        
        p.drawImage(ImageReader(qr_buffer), qr_x, qr_y, width=qr_size, height=qr_size, mask='auto')
        
        # Save verification QR separately if needed for preview
        qr_buffer.seek(0)
        cert.verification_qr.save(f"qr_{cert.certificate_id}.png", ContentFile(qr_buffer.getvalue()), save=False)
    
    # 4. Finalize PDF
    p.showPage()
    p.save()
    
    # 5. Save to model
    pdf_filename = f"cert_{cert.certificate_id}.pdf"
    cert.pdf_file.save(pdf_filename, ContentFile(buffer.getvalue()), save=False)
    
    cert.status = 'completed'
    cert.save()
    return cert.pdf_file.url


def generate_certificate_image(cert_id, dpi=300):
    """
    Renders a pixel-perfect, ultra high-resolution PNG image directly
    from the certificate's PDF at the requested DPI (default 300 DPI for print & sharing).
    Returns bytes of the PNG image.
    """
    cert = Certificate.objects.get(id=cert_id)
    if not cert.pdf_file or not os.path.exists(cert.pdf_file.path):
        generate_certificate_pdf(cert.id)
        cert.refresh_from_db()
        
    doc = fitz.open(cert.pdf_file.path)
    try:
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes(output='png')
    finally:
        doc.close()

