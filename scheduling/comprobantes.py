import uuid
from datetime import date, datetime, time, timezone as dt_timezone
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PRIMARY_COLOR = (0x3A / 255, 0xBA / 255, 0xD1 / 255)
DARK_COLOR = (0x1F / 255, 0x29 / 255, 0x37 / 255)
GRAY_COLOR = (0x5B / 255, 0x64 / 255, 0x70 / 255)


def generar_pdf_comprobante(resumen, clinic_info):
    """
    Comprobante de la cita reservada, en PDF. `resumen` es el dict guardado en
    sesión al confirmar la reserva (ver reservar_resumen). No incluye ningún
    comprobante de pago real: el anticipo se coordina fuera del sistema.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    margen = 20 * mm
    y = alto - margen

    nombre_clinica = clinic_info.nombre if clinic_info else "Dental San Antonio"

    c.setFillColorRGB(*PRIMARY_COLOR)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margen, y, nombre_clinica)
    y -= 10 * mm

    c.setFillColorRGB(*DARK_COLOR)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margen, y, "Comprobante de cita")
    y -= 6 * mm

    c.setStrokeColorRGB(*PRIMARY_COLOR)
    c.setLineWidth(1)
    c.line(margen, y, ancho - margen, y)
    y -= 10 * mm

    def fila(etiqueta, valor, tamano_valor=12, negritas=False):
        nonlocal y
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(*GRAY_COLOR)
        c.drawString(margen, y, etiqueta)
        c.setFont("Helvetica-Bold" if negritas else "Helvetica", tamano_valor)
        c.setFillColorRGB(*DARK_COLOR)
        c.drawString(margen, y - 5.5 * mm, str(valor))
        y -= 14 * mm

    fila("Paciente", resumen.get("nombre", ""))
    fila("Servicio", resumen.get("servicio", ""))
    fila("Fecha y hora", f"{resumen.get('fecha', '')} — {resumen.get('hora_inicio', '')} a {resumen.get('hora_fin', '')}")
    fila("Precio total", f"${resumen.get('precio_final', '')} MXN", tamano_valor=14, negritas=True)
    fila(
        f"Anticipo requerido ({resumen.get('anticipo_porcentaje', '')}%)",
        f"${resumen.get('anticipo_requerido', '')} MXN",
        tamano_valor=14,
        negritas=True,
    )

    y -= 4 * mm
    c.setFillColorRGB(*GRAY_COLOR)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        margen, y,
        "Esta cita queda pendiente de confirmación hasta coordinar el pago del anticipo.",
    )
    y -= 12 * mm

    c.setStrokeColorRGB(0.85, 0.9, 0.91)
    c.line(margen, y, ancho - margen, y)
    y -= 8 * mm

    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(*DARK_COLOR)
    c.drawString(margen, y, "¿Dudas o necesitas hacer algún cambio?")
    y -= 6 * mm

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*GRAY_COLOR)
    if clinic_info:
        if clinic_info.telefono_1:
            c.drawString(margen, y, f"Teléfono: {clinic_info.telefono_1}")
            y -= 5.5 * mm
        if clinic_info.telefono_2:
            c.drawString(margen, y, f"Teléfono: {clinic_info.telefono_2}")
            y -= 5.5 * mm
        if clinic_info.email:
            c.drawString(margen, y, f"Correo: {clinic_info.email}")
            y -= 5.5 * mm
        if clinic_info.direccion:
            c.drawString(margen, y, f"Dirección: {clinic_info.direccion}")
            y -= 5.5 * mm

    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*GRAY_COLOR)
    c.drawString(
        margen, margen / 2,
        f"Generado el {timezone.localtime():%d/%m/%Y %H:%M}",
    )

    c.showPage()
    c.save()
    return buffer.getvalue()


def generar_ics_comprobante(resumen, clinic_info):
    """
    Archivo .ics de la cita para agregar al calendario del teléfono
    (Google Calendar en Android, Calendario en iPhone). No requiere ninguna
    cuenta ni certificado especial, a diferencia de un pase de Apple Wallet.
    """
    fecha = date.fromisoformat(resumen["fecha_iso"])
    hora_inicio = time.fromisoformat(resumen["hora_inicio"])
    hora_fin = time.fromisoformat(resumen["hora_fin"])
    inicio_dt = datetime.combine(fecha, hora_inicio)
    fin_dt = datetime.combine(fecha, hora_fin)

    telefono = clinic_info.telefono_1 if clinic_info else ""
    direccion = clinic_info.direccion if clinic_info else ""
    nombre_clinica = clinic_info.nombre if clinic_info else "Dental San Antonio"

    descripcion = (
        f"Servicio: {resumen.get('servicio', '')}. "
        f"Anticipo requerido: ${resumen.get('anticipo_requerido', '')} MXN. "
        f"Dudas o cambios: {telefono}"
    ).replace(",", "\\,")

    ahora_utc = timezone.now().astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lineas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Dental San Antonio//Cita//ES",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@dentalsanantonio",
        f"DTSTAMP:{ahora_utc}",
        f"DTSTART:{inicio_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{fin_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:Cita dental — {resumen.get('servicio', '')}",
        f"DESCRIPTION:{descripcion}",
        f"LOCATION:{direccion}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lineas)
