from django.urls import path

from . import views

app_name = "scheduling"

urlpatterns = [
    path("reservar/", views.reservar_categoria, name="reservar_categoria"),
    path("reservar/servicio/", views.reservar_servicio, name="reservar_servicio"),
    path("reservar/fecha/", views.reservar_fecha, name="reservar_fecha"),
    path("reservar/horario/", views.reservar_horario, name="reservar_horario"),
    path("reservar/datos/", views.reservar_datos, name="reservar_datos"),
    path("reservar/convenio/", views.reservar_convenio, name="reservar_convenio"),
    path("reservar/dolor/", views.reservar_dolor, name="reservar_dolor"),
    path("reservar/resumen/", views.reservar_resumen, name="reservar_resumen"),
    path("reservar/confirmacion/", views.reserva_confirmacion, name="reserva_confirmacion"),
    path("reservar/confirmacion/comprobante.pdf", views.reserva_comprobante_pdf, name="reserva_comprobante_pdf"),
    path("reservar/confirmacion/cita.ics", views.reserva_comprobante_ics, name="reserva_comprobante_ics"),

    path("emergencia/", views.emergencia_formulario, name="emergencia_formulario"),
    path("emergencia/confirmacion/", views.emergencia_confirmacion, name="emergencia_confirmacion"),

    path("panel/", views.panel_dashboard, name="panel_dashboard"),
    path("panel/agenda/", views.panel_agenda, name="panel_agenda"),
    path("panel/citas/buscar/", views.panel_buscar_citas, name="panel_buscar_citas"),
    path("panel/citas/nueva/", views.panel_cita_nueva, name="panel_cita_nueva"),
    path("panel/citas/<int:cita_id>/estado/", views.panel_cambiar_estado, name="panel_cambiar_estado"),
    path("panel/citas/<int:cita_id>/anticipo/", views.panel_cambiar_estado_anticipo, name="panel_cambiar_estado_anticipo"),
    path("panel/disponibilidad/", views.panel_disponibilidad, name="panel_disponibilidad"),
    path("panel/disponibilidad/bloqueos/<int:bloqueo_id>/desactivar/", views.panel_bloqueo_desactivar, name="panel_bloqueo_desactivar"),
    path("panel/emergencias/", views.panel_emergencias, name="panel_emergencias"),
    path("panel/emergencias/<int:solicitud_id>/estado/", views.panel_solicitud_cambiar_estado, name="panel_solicitud_cambiar_estado"),
]
