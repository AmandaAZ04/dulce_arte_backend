from io import BytesIO
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode
from .models import Aviso

def enlace(pedido): return f'{settings.PUBLIC_BASE_URL}/seguimiento/{pedido.token}/'
def qr_png(pedido):
    out=BytesIO(); qrcode.make(enlace(pedido)).save(out,format='PNG'); return out.getvalue()

def comprobante(p):
    out=BytesIO(); c=canvas.Canvas(out,pagesize=(420,595))
    c.setTitle(f'Comprobante {p.codigo} · Dulce Arte')
    c.setFillColorRGB(.27,.19,.16); c.setFont('Times-Bold',32); c.drawString(35,545,'Dulce Arte')
    c.setFont('Helvetica',10); c.drawString(35,522,'Pastelería artesanal · Retiro en el local')
    c.setStrokeColorRGB(.8,.72,.65); c.line(35,502,385,502)
    lines=[f'COMPROBANTE DE PEDIDO {p.codigo}', f'Cliente: {p.cliente.get_full_name() or p.cliente.username}',f'Producto: {p.producto}',f'Cantidad: {p.cantidad}',f'Total: $ {p.total:,.0f} CLP'.replace(',','.'),f'Estado: {p.get_estado_display()}',f'Pago: {"recibido en local" if p.pagado else "pendiente en local"}',f'Retiro: {timezone.localtime(p.retiro):%d/%m/%Y %H:%M}',settings.LOCAL_ADDRESS]
    for n,line in enumerate(lines): c.drawString(35,475-n*23,line[:72])
    c.drawImage(ImageReader(BytesIO(qr_png(p))),135,90,150,150)
    c.setFont('Helvetica',9); c.drawCentredString(210,73,'Presenta este QR al retirar tu pedido.')
    c.setFont('Helvetica',8); c.drawCentredString(210,43,'Comprobante de pedido. No constituye boleta tributaria.')
    c.save(); return out.getvalue()

def enviar_aviso(aviso_id):
    # Serializa reintentos. SMTP no garantiza entrega exactamente una vez ante cortes.
    with transaction.atomic():
        aviso=Aviso.objects.select_for_update().select_related('pedido__cliente').get(pk=aviso_id)
        if aviso.enviado: return
        p=aviso.pedido; aviso.intentos+=1
        try:
            body=f'Hola {p.cliente.first_name or p.cliente.username},\n\nTu pedido {p.codigo} está en estado: {p.get_estado_display()}.\nProducto: {p.producto} x {p.cantidad}\nTotal: ${p.total} CLP\nRetiro: {timezone.localtime(p.retiro):%d/%m/%Y %H:%M}\n{settings.LOCAL_ADDRESS}\n\nRevisa el estado: {enlace(p)}\nEl QR es personal: preséntalo al retirar.\n\nAdjuntamos el comprobante de pedido (no tributario).\nCon cariño, Dulce Arte'
            mail=EmailMessage(f'{p.codigo} · {p.get_estado_display()} · Dulce Arte',body,settings.DEFAULT_FROM_EMAIL,[p.cliente.email])
            mail.attach(f'{p.codigo}.pdf',comprobante(p),'application/pdf')
            mail.attach(f'{p.codigo}-QR.png',qr_png(p),'image/png')
            if mail.send()!=1: raise RuntimeError('El servidor no aceptó el mensaje.')
            aviso.enviado=True; aviso.error=''
        except Exception as exc:
            aviso.error=type(exc).__name__ + ': revisa la configuración de correo.'
        aviso.save(update_fields=['enviado','intentos','error'])
