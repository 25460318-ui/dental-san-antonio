from django.utils import timezone

from .models import Aviso, SolicitudEmergencia


def solicitudes_pendientes(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "solicitudes_emergencia_pendientes": SolicitudEmergencia.objects.filter(
            estado=SolicitudEmergencia.Estado.PENDIENTE
        ).count()
    }


def avisos_publicos(request):
    ahora = timezone.now()
    return {
        "avisos_publicos": Aviso.objects.filter(
            activo=True,
            fecha_inicio_publicacion__lte=ahora,
            fecha_fin_publicacion__gte=ahora,
        ).order_by("fecha_inicio_publicacion")
    }
