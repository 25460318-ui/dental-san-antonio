import logging

from django.core.mail import send_mail

from core.models import ClinicInfo

logger = logging.getLogger(__name__)


def _contacto(clinic_info):
    if not clinic_info:
        return ""
    partes = [p for p in [clinic_info.telefono_1, clinic_info.email] if p]
    return " / ".join(partes)


def _enviar(destinatario, asunto, cuerpo):
    if not destinatario:
        return
    try:
        send_mail(asunto, cuerpo, None, [destinatario], fail_silently=False)
    except Exception:
        # Un correo que falla (por ejemplo, credenciales SMTP mal
        # configuradas en producción) no debe tumbar la reserva ni el
        # cambio de estado del anticipo; solo se registra en el log.
        logger.exception("No se pudo enviar el correo a %s", destinatario)


def enviar_confirmacion_cita(cita):
    if not cita.paciente.email:
        return
    clinic_info = ClinicInfo.objects.first()
    asunto = "Tu cita en Dental San Antonio quedó registrada"
    cuerpo = (
        f"Hola {cita.paciente.nombre},\n\n"
        f"Registramos tu cita:\n"
        f"Servicio: {cita.servicio.nombre}\n"
        f"Fecha: {cita.fecha:%d/%m/%Y}\n"
        f"Hora: {cita.hora_inicio:%H:%M} - {cita.hora_fin:%H:%M}\n"
        f"Precio: ${cita.precio_final} MXN\n"
        f"Anticipo requerido: ${cita.anticipo_requerido} MXN\n\n"
        f"Tu cita está pendiente de confirmación hasta coordinar el anticipo.\n\n"
        f"¿Dudas o necesitas hacer un cambio? Contáctanos: {_contacto(clinic_info)}\n\n"
        f"— {clinic_info.nombre if clinic_info else 'Dental San Antonio'}"
    )
    _enviar(cita.paciente.email, asunto, cuerpo)


def enviar_alerta_secretaria_nueva_emergencia(solicitud):
    """Avisa al correo del consultorio que llegó una solicitud de emergencia."""
    clinic_info = ClinicInfo.objects.first()
    if not clinic_info or not clinic_info.email:
        return
    asunto = f"🚨 Nueva emergencia: {solicitud.nombre}"
    cuerpo = (
        f"Llegó una solicitud de emergencia:\n\n"
        f"Paciente: {solicitud.nombre}\n"
        f"Teléfono: {solicitud.telefono}\n"
        f"Nivel de dolor: {solicitud.nivel_dolor}/10\n"
        f"Motivo: {solicitud.motivo}\n\n"
        f"Revísala y contáctalo desde el panel, en Emergencias."
    )
    _enviar(clinic_info.email, asunto, cuerpo)


def enviar_alerta_secretaria_anticipo_emergencia(cita):
    """Avisa al correo del consultorio que se confirmó el pago de una emergencia."""
    clinic_info = ClinicInfo.objects.first()
    if not clinic_info or not clinic_info.email:
        return
    asunto = f"Anticipo de emergencia confirmado: {cita.paciente.nombre}"
    cuerpo = (
        f"Se confirmó el pago del anticipo de una cita de emergencia:\n\n"
        f"Paciente: {cita.paciente.nombre}\n"
        f"Teléfono: {cita.paciente.telefono}\n"
        f"Servicio: {cita.servicio.nombre}\n"
        f"Fecha: {cita.fecha:%d/%m/%Y} {cita.hora_inicio:%H:%M}\n"
        f"Anticipo: ${cita.anticipo_requerido} MXN\n"
    )
    _enviar(clinic_info.email, asunto, cuerpo)


def enviar_confirmacion_anticipo(cita):
    if not cita.paciente.email:
        return
    clinic_info = ClinicInfo.objects.first()
    asunto = "Confirmamos tu anticipo — Dental San Antonio"
    cuerpo = (
        f"Hola {cita.paciente.nombre},\n\n"
        f"Confirmamos que recibimos tu anticipo de ${cita.anticipo_requerido} MXN "
        f"para tu cita de {cita.servicio.nombre} el {cita.fecha:%d/%m/%Y} "
        f"a las {cita.hora_inicio:%H:%M}.\n\n"
        f"Tu cita ya está confirmada. Te esperamos.\n\n"
        f"¿Dudas o necesitas hacer un cambio? Contáctanos: {_contacto(clinic_info)}\n\n"
        f"— {clinic_info.nombre if clinic_info else 'Dental San Antonio'}"
    )
    _enviar(cita.paciente.email, asunto, cuerpo)
