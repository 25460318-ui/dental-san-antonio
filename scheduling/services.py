from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from catalog.models import PrecioConvenio

from .models import BloqueoAgenda, Cita, HorarioAtencion

SLOT_MINUTOS_DEFAULT = 30


class HorarioNoDisponibleError(Exception):
    """El horario solicitado ya no está disponible (cita o bloqueo encimados)."""


def hay_conflicto(fecha, hora_inicio, hora_fin, excluir_cita_id=None):
    """
    True si el intervalo [hora_inicio, hora_fin) de `fecha` se encima con una
    cita activa (online o presencial, da igual el origen) o con un bloqueo de
    agenda. Esta es la única función que decide disponibilidad real: tanto
    reservar en línea como registrar una cita presencial deben pasar por aquí.
    """
    citas = Cita.objects.filter(
        fecha=fecha,
        hora_inicio__lt=hora_fin,
        hora_fin__gt=hora_inicio,
    ).exclude(estado_cita=Cita.EstadoCita.CANCELADA)
    if excluir_cita_id:
        citas = citas.exclude(pk=excluir_cita_id)
    if citas.exists():
        return True

    inicio_dt = timezone.make_aware(datetime.combine(fecha, hora_inicio))
    fin_dt = timezone.make_aware(datetime.combine(fecha, hora_fin))
    return BloqueoAgenda.objects.filter(
        activo=True,
        fecha_hora_inicio__lt=fin_dt,
        fecha_hora_fin__gt=inicio_dt,
    ).exists()


def franjas_disponibles(fecha, duracion_minutos=SLOT_MINUTOS_DEFAULT):
    """
    Lista de horarios libres (hora_inicio, hora_fin) para `fecha`, ya
    descontando bloqueos y citas existentes. `duracion_minutos` normalmente
    viene de `servicio.duracion_minutos`; si el servicio no tiene duración
    definida todavía, se usa un slot de 30 minutos por defecto.
    """
    duracion = duracion_minutos or SLOT_MINUTOS_DEFAULT
    paso = timedelta(minutes=duracion)
    horarios = HorarioAtencion.objects.filter(dia_semana=fecha.weekday())

    slots = []
    for bloque in horarios:
        cursor = datetime.combine(fecha, bloque.hora_inicio)
        fin_bloque = datetime.combine(fecha, bloque.hora_fin)
        while cursor + paso <= fin_bloque:
            inicio = cursor.time()
            fin = (cursor + paso).time()
            if not hay_conflicto(fecha, inicio, fin):
                slots.append((inicio, fin))
            cursor += paso
    return slots


def citas_afectadas_por_bloqueo(fecha_hora_inicio, fecha_hora_fin, excluir_bloqueo_id=None):
    """
    Citas activas que quedarían dentro de un bloqueo de agenda propuesto.
    Se usa para avisar al doctor/secretaria ANTES de confirmar un bloqueo que
    ya tiene pacientes agendados en ese rango, para que puedan reprogramarlos
    en vez de que el bloqueo simplemente los deje "atrapados" en silencio.
    """
    fecha_inicio = fecha_hora_inicio.date()
    fecha_fin = fecha_hora_fin.date()

    candidatas = Cita.objects.filter(
        fecha__gte=fecha_inicio, fecha__lte=fecha_fin
    ).exclude(estado_cita=Cita.EstadoCita.CANCELADA).select_related("paciente", "servicio")

    afectadas = []
    for cita in candidatas:
        inicio_dt = timezone.make_aware(datetime.combine(cita.fecha, cita.hora_inicio))
        fin_dt = timezone.make_aware(datetime.combine(cita.fecha, cita.hora_fin))
        if inicio_dt < fecha_hora_fin and fecha_hora_inicio < fin_dt:
            afectadas.append(cita)
    return afectadas


def calcular_cotizacion(servicio, convenio, nivel_dolor, clinic_info):
    """
    Fotografía económica de una cita: precio del servicio, descuento por
    convenio (si aplica), recargo por dolor alto (si aplica) y anticipo
    requerido. Los mismos valores se guardan en la Cita al confirmarla, para
    que un cambio posterior de precios no afecte citas ya reservadas.
    """
    precio_original = servicio.precio_general
    precio_convenio = None
    if convenio is not None:
        precio_convenio = PrecioConvenio.objects.filter(servicio=servicio, convenio=convenio).first()
    precio_base = precio_convenio.precio_especial if precio_convenio else precio_original
    descuento = precio_original - precio_base

    recargo_dolor = Decimal("0")
    if nivel_dolor is not None and nivel_dolor >= clinic_info.dolor_umbral_recargo:
        recargo_dolor = clinic_info.dolor_recargo_monto

    precio_final = precio_base + recargo_dolor
    anticipo_porcentaje = clinic_info.anticipo_porcentaje
    anticipo_requerido = (precio_final * anticipo_porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    return {
        "precio_original": precio_original,
        "descuento": descuento,
        "recargo_dolor": recargo_dolor,
        "precio_final": precio_final,
        "anticipo_porcentaje": anticipo_porcentaje,
        "anticipo_requerido": anticipo_requerido,
    }
