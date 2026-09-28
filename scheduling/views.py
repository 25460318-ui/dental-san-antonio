from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from catalog.models import CategoriaServicio, Convenio, Servicio
from core.models import ClinicInfo

from .comprobantes import generar_ics_comprobante, generar_pdf_comprobante
from .notificaciones import (
    enviar_alerta_secretaria_anticipo_emergencia,
    enviar_alerta_secretaria_nueva_emergencia,
    enviar_confirmacion_anticipo,
    enviar_confirmacion_cita,
)
from .forms import (
    BloqueoForm,
    CategoriaForm,
    ConvenioForm,
    DatosPacienteForm,
    DolorForm,
    EmergenciaForm,
    EstadoAnticipoForm,
    EstadoCitaForm,
    EstadoSolicitudForm,
    FechaForm,
    HorarioForm,
    RegistroPresencialForm,
    ServicioFechaForm,
    ServicioForm,
)
from .models import Aviso, BloqueoAgenda, Cita, HorarioAtencion, Paciente, SolicitudEmergencia
from .services import calcular_cotizacion, citas_afectadas_por_bloqueo, franjas_disponibles, hay_conflicto

SESSION_KEY = "reserva"


def _wizard(request):
    return request.session.setdefault(SESSION_KEY, {})


def _requiere(request, *claves):
    data = request.session.get(SESSION_KEY, {})
    return all(clave in data for clave in claves)


def reservar_categoria(request):
    clinic_info = ClinicInfo.objects.first()
    if clinic_info and not clinic_info.reservas_online_activas:
        return render(request, "scheduling/reservas_pausadas.html", {"clinic_info": clinic_info})

    preseleccion = request.GET.get("categoria")
    if preseleccion and request.method == "GET" and CategoriaServicio.objects.filter(pk=preseleccion).exists():
        wizard = _wizard(request)
        wizard.clear()
        wizard["categoria_id"] = int(preseleccion)
        request.session.modified = True
        return redirect("scheduling:reservar_servicio")

    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            wizard = _wizard(request)
            wizard.clear()
            wizard["categoria_id"] = form.cleaned_data["categoria"].pk
            request.session.modified = True
            return redirect("scheduling:reservar_servicio")
    else:
        form = CategoriaForm()
    return render(request, "scheduling/reservar_categoria.html", {"form": form, "paso": 1})


def reservar_servicio(request):
    if not _requiere(request, "categoria_id"):
        return redirect("scheduling:reservar_categoria")
    categoria = get_object_or_404(CategoriaServicio, pk=request.session[SESSION_KEY]["categoria_id"])

    if request.method == "POST":
        form = ServicioForm(request.POST, categoria=categoria)
        if form.is_valid():
            wizard = _wizard(request)
            wizard["servicio_id"] = form.cleaned_data["servicio"].pk
            request.session.modified = True
            return redirect("scheduling:reservar_fecha")
    else:
        form = ServicioForm(categoria=categoria)
    return render(request, "scheduling/reservar_servicio.html", {
        "form": form, "categoria": categoria, "servicios": form.fields["servicio"].queryset, "paso": 2,
    })


def reservar_fecha(request):
    if not _requiere(request, "servicio_id"):
        return redirect("scheduling:reservar_categoria")
    servicio = get_object_or_404(Servicio, pk=request.session[SESSION_KEY]["servicio_id"])

    form = FechaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fecha = form.cleaned_data["fecha"]
        slots = franjas_disponibles(fecha, servicio.duracion_minutos)
        if not slots:
            form.add_error("fecha", "No hay horarios disponibles ese día. Elige otra fecha.")
        else:
            wizard = _wizard(request)
            wizard["fecha"] = fecha.isoformat()
            wizard.pop("hora_inicio", None)
            wizard.pop("hora_fin", None)
            request.session.modified = True
            return redirect("scheduling:reservar_horario")

    return render(request, "scheduling/reservar_fecha.html", {"form": form, "servicio": servicio, "paso": 3})


def reservar_horario(request):
    if not _requiere(request, "servicio_id", "fecha"):
        return redirect("scheduling:reservar_categoria")
    wizard = _wizard(request)
    servicio = get_object_or_404(Servicio, pk=wizard["servicio_id"])
    fecha = date.fromisoformat(wizard["fecha"])
    slots = franjas_disponibles(fecha, servicio.duracion_minutos)

    choices = [
        (f"{inicio.isoformat()}|{fin.isoformat()}", f'{inicio.strftime("%H:%M")} - {fin.strftime("%H:%M")}')
        for inicio, fin in slots
    ]

    form = HorarioForm(request.POST or None, choices=choices)
    if request.method == "POST" and form.is_valid():
        inicio_str, fin_str = form.cleaned_data["horario"].split("|")
        wizard["hora_inicio"] = inicio_str
        wizard["hora_fin"] = fin_str
        request.session.modified = True
        return redirect("scheduling:reservar_datos")

    return render(request, "scheduling/reservar_horario.html", {
        "form": form, "servicio": servicio, "fecha": fecha, "paso": 4, "hay_slots": bool(choices),
    })


def reservar_datos(request):
    if not _requiere(request, "servicio_id", "fecha", "hora_inicio"):
        return redirect("scheduling:reservar_categoria")
    wizard = _wizard(request)

    if request.method == "POST":
        form = DatosPacienteForm(request.POST)
        if form.is_valid():
            wizard.update(form.cleaned_data)
            request.session.modified = True
            return redirect("scheduling:reservar_convenio")
    else:
        initial = {k: wizard.get(k) for k in ("nombre", "telefono", "email")}
        form = DatosPacienteForm(initial=initial)
    return render(request, "scheduling/reservar_datos.html", {"form": form, "paso": 5})


def reservar_convenio(request):
    if not _requiere(request, "servicio_id", "fecha", "hora_inicio", "nombre"):
        return redirect("scheduling:reservar_categoria")
    wizard = _wizard(request)

    if request.method == "POST":
        form = ConvenioForm(request.POST)
        if form.is_valid():
            convenio = form.cleaned_data["convenio"]
            wizard["convenio_id"] = convenio.pk if convenio else None
            wizard["identificador_convenio"] = form.cleaned_data["identificador_convenio"]
            request.session.modified = True
            return redirect("scheduling:reservar_dolor")
    else:
        initial = {}
        if wizard.get("convenio_id"):
            initial["convenio"] = wizard["convenio_id"]
        initial["identificador_convenio"] = wizard.get("identificador_convenio", "")
        form = ConvenioForm(initial=initial)
    return render(request, "scheduling/reservar_convenio.html", {"form": form, "paso": 6})


def reservar_dolor(request):
    if not _requiere(request, "servicio_id", "fecha", "hora_inicio", "nombre"):
        return redirect("scheduling:reservar_categoria")
    wizard = _wizard(request)

    if request.method == "POST":
        form = DolorForm(request.POST)
        if form.is_valid():
            wizard["nivel_dolor"] = form.cleaned_data["nivel_dolor"]
            request.session.modified = True
            return redirect("scheduling:reservar_resumen")
    else:
        form = DolorForm(initial={"nivel_dolor": wizard.get("nivel_dolor", 0)})
    return render(request, "scheduling/reservar_dolor.html", {"form": form, "paso": 7})


def reservar_resumen(request):
    if not _requiere(request, "servicio_id", "fecha", "hora_inicio", "nombre", "nivel_dolor"):
        return redirect("scheduling:reservar_categoria")
    wizard = _wizard(request)
    clinic_info = ClinicInfo.objects.first()

    if clinic_info and not clinic_info.reservas_online_activas:
        return render(request, "scheduling/reservas_pausadas.html", {"clinic_info": clinic_info})

    servicio = get_object_or_404(Servicio, pk=wizard["servicio_id"])
    fecha = date.fromisoformat(wizard["fecha"])
    hora_inicio = time.fromisoformat(wizard["hora_inicio"])
    hora_fin = time.fromisoformat(wizard["hora_fin"])
    convenio = None
    if wizard.get("convenio_id"):
        convenio = Convenio.objects.filter(pk=wizard["convenio_id"]).first()
    nivel_dolor = wizard["nivel_dolor"]

    cotizacion = calcular_cotizacion(servicio, convenio, nivel_dolor, clinic_info)

    context = {
        "paso": 8,
        "servicio": servicio,
        "fecha": fecha,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "convenio": convenio,
        "nivel_dolor": nivel_dolor,
        "nombre": wizard["nombre"],
        "telefono": wizard["telefono"],
        "email": wizard.get("email"),
        **cotizacion,
    }

    if request.method == "POST":
        if hay_conflicto(fecha, hora_inicio, hora_fin):
            messages.error(request, "Ese horario ya no está disponible. Por favor elige otro.")
            return redirect("scheduling:reservar_horario")

        try:
            with transaction.atomic():
                paciente, _creado = Paciente.objects.update_or_create(
                    telefono=wizard["telefono"],
                    defaults={
                        "nombre": wizard["nombre"],
                        "email": wizard.get("email", ""),
                        "convenio": convenio,
                        "identificador_convenio": wizard.get("identificador_convenio", ""),
                    },
                )
                cita = Cita.objects.create(
                    paciente=paciente,
                    servicio=servicio,
                    convenio=convenio,
                    origen=Cita.Origen.ONLINE,
                    tipo=Cita.Tipo.REGULAR,
                    fecha=fecha,
                    hora_inicio=hora_inicio,
                    hora_fin=hora_fin,
                    precio_original=cotizacion["precio_original"],
                    descuento=cotizacion["descuento"],
                    recargo_dolor=cotizacion["recargo_dolor"],
                    precio_final=cotizacion["precio_final"],
                    anticipo_porcentaje_aplicado=cotizacion["anticipo_porcentaje"],
                    anticipo_requerido=cotizacion["anticipo_requerido"],
                    nivel_dolor=nivel_dolor,
                )
        except IntegrityError:
            messages.error(request, "Ese horario ya no está disponible. Por favor elige otro.")
            return redirect("scheduling:reservar_horario")

        enviar_confirmacion_cita(cita)

        request.session["reserva_confirmada"] = {
            "nombre": wizard["nombre"],
            "servicio": servicio.nombre,
            "fecha": fecha.strftime("%d/%m/%Y"),
            "fecha_iso": fecha.isoformat(),
            "hora_inicio": hora_inicio.strftime("%H:%M"),
            "hora_fin": hora_fin.strftime("%H:%M"),
            "precio_final": str(cotizacion["precio_final"]),
            "anticipo_requerido": str(cotizacion["anticipo_requerido"]),
            "anticipo_porcentaje": str(cotizacion["anticipo_porcentaje"]),
        }
        del request.session[SESSION_KEY]
        return redirect("scheduling:reserva_confirmacion")

    return render(request, "scheduling/reservar_resumen.html", context)


def reserva_confirmacion(request):
    resumen = request.session.get("reserva_confirmada")
    if not resumen:
        return redirect("scheduling:reservar_categoria")
    return render(request, "scheduling/reserva_confirmacion.html", {"resumen": resumen})


def reserva_comprobante_pdf(request):
    resumen = request.session.get("reserva_confirmada")
    if not resumen:
        return redirect("scheduling:reservar_categoria")
    clinic_info = ClinicInfo.objects.first()
    pdf_bytes = generar_pdf_comprobante(resumen, clinic_info)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="comprobante-cita-dental-san-antonio.pdf"'
    return response


def reserva_comprobante_ics(request):
    resumen = request.session.get("reserva_confirmada")
    if not resumen:
        return redirect("scheduling:reservar_categoria")
    clinic_info = ClinicInfo.objects.first()
    contenido = generar_ics_comprobante(resumen, clinic_info)
    response = HttpResponse(contenido, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cita-dental-san-antonio.ics"'
    return response


# --- Emergencias (público) ---


def emergencia_formulario(request):
    clinic_info = ClinicInfo.objects.first()
    form = EmergenciaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        solicitud = SolicitudEmergencia.objects.create(**form.cleaned_data)
        enviar_alerta_secretaria_nueva_emergencia(solicitud)
        request.session["emergencia_confirmada"] = True
        return redirect("scheduling:emergencia_confirmacion")
    return render(request, "scheduling/emergencia_formulario.html", {"form": form, "clinic_info": clinic_info})


def emergencia_confirmacion(request):
    if not request.session.pop("emergencia_confirmada", None):
        return redirect("scheduling:emergencia_formulario")
    return render(request, "scheduling/emergencia_confirmacion.html")


# --- Panel privado (secretaria / doctor) ---


@login_required
@permission_required("scheduling.view_cita", raise_exception=True)
def panel_agenda(request):
    fecha_str = request.GET.get("fecha")
    fecha = date.fromisoformat(fecha_str) if fecha_str else timezone.localdate()

    citas = Cita.objects.filter(fecha=fecha).select_related("paciente", "servicio", "convenio")

    origen = request.GET.get("origen")
    if origen:
        citas = citas.filter(origen=origen)
    tipo = request.GET.get("tipo")
    if tipo:
        citas = citas.filter(tipo=tipo)
    estado = request.GET.get("estado")
    if estado:
        citas = citas.filter(estado_cita=estado)
    servicio_id = request.GET.get("servicio")
    if servicio_id:
        citas = citas.filter(servicio_id=servicio_id)
    dolor_min = request.GET.get("dolor_min")
    if dolor_min:
        citas = citas.filter(nivel_dolor__gte=dolor_min)
    estado_anticipo = request.GET.get("estado_anticipo")
    if estado_anticipo:
        citas = citas.filter(estado_anticipo=estado_anticipo)

    citas = citas.order_by("hora_inicio")

    context = {
        "fecha": fecha,
        "citas": citas,
        "servicios": Servicio.objects.filter(activo=True),
        "origenes": Cita.Origen.choices,
        "tipos": Cita.Tipo.choices,
        "estados": Cita.EstadoCita.choices,
        "estados_anticipo": Cita.EstadoAnticipo.choices,
        "filtros": request.GET,
        "dia_anterior": fecha - timedelta(days=1),
        "dia_siguiente": fecha + timedelta(days=1),
    }
    return render(request, "scheduling/panel_agenda.html", context)


@login_required
@permission_required("scheduling.change_cita", raise_exception=True)
def panel_cambiar_estado(request, cita_id):
    cita = get_object_or_404(Cita, pk=cita_id)
    if request.method == "POST":
        form = EstadoCitaForm(request.POST)
        if form.is_valid():
            cita.estado_cita = form.cleaned_data["estado_cita"]
            cita.save(update_fields=["estado_cita"])
            messages.success(request, "Estado de la cita actualizado.")
    next_url = request.POST.get("next") or reverse("scheduling:panel_agenda")
    return redirect(next_url)


@login_required
@permission_required("scheduling.change_cita", raise_exception=True)
def panel_cambiar_estado_anticipo(request, cita_id):
    cita = get_object_or_404(Cita, pk=cita_id)
    if request.method == "POST":
        form = EstadoAnticipoForm(request.POST)
        if form.is_valid():
            estado_anterior = cita.estado_anticipo
            cita.estado_anticipo = form.cleaned_data["estado_anticipo"]
            update_fields = ["estado_anticipo"]
            # Recibir el anticipo confirma la cita: ya no tiene sentido dejarla
            # "pendiente de confirmación" si el paciente ya pagó.
            if (
                cita.estado_anticipo == Cita.EstadoAnticipo.PAGADO
                and cita.estado_cita == Cita.EstadoCita.PENDIENTE_CONFIRMACION
            ):
                cita.estado_cita = Cita.EstadoCita.CONFIRMADA
                update_fields.append("estado_cita")
            cita.save(update_fields=update_fields)
            if (
                cita.estado_anticipo == Cita.EstadoAnticipo.PAGADO
                and estado_anterior != Cita.EstadoAnticipo.PAGADO
            ):
                enviar_confirmacion_anticipo(cita)
                if cita.tipo == Cita.Tipo.EMERGENCIA:
                    enviar_alerta_secretaria_anticipo_emergencia(cita)
            messages.success(request, "Estado del anticipo actualizado.")
    next_url = request.POST.get("next") or reverse("scheduling:panel_agenda")
    return redirect(next_url)


@login_required
@permission_required("scheduling.add_cita", raise_exception=True)
def panel_cita_nueva(request):
    buscar_form = ServicioFechaForm(request.GET or None)
    servicio = None
    fecha = None
    slots = []

    solicitud_id = request.GET.get("solicitud") or request.POST.get("solicitud_id")
    solicitud = SolicitudEmergencia.objects.filter(pk=solicitud_id).first() if solicitud_id else None

    if request.method == "GET" and buscar_form.is_valid():
        servicio = buscar_form.cleaned_data["servicio"]
        fecha = buscar_form.cleaned_data["fecha"]
        slots = franjas_disponibles(fecha, servicio.duracion_minutos)

    initial = {}
    if solicitud and request.method == "GET":
        initial = {
            "nombre": solicitud.nombre,
            "telefono": solicitud.telefono,
            "nivel_dolor": solicitud.nivel_dolor,
            "tipo": Cita.Tipo.EMERGENCIA,
        }
    registro_form = RegistroPresencialForm(request.POST or None, initial=initial)

    if request.method == "POST":
        servicio_id = request.POST.get("servicio_id")
        fecha_str = request.POST.get("fecha_valor")
        horario = request.POST.get("horario")
        servicio = get_object_or_404(Servicio, pk=servicio_id) if servicio_id else None
        fecha = date.fromisoformat(fecha_str) if fecha_str else None

        if servicio and fecha:
            slots = franjas_disponibles(fecha, servicio.duracion_minutos)

        if registro_form.is_valid() and servicio and fecha and horario:
            hora_inicio_str, hora_fin_str = horario.split("|")
            hora_inicio = time.fromisoformat(hora_inicio_str)
            hora_fin = time.fromisoformat(hora_fin_str)

            if hay_conflicto(fecha, hora_inicio, hora_fin):
                messages.error(request, "Ese horario ya no está disponible. Elige otro.")
            else:
                clinic_info = ClinicInfo.objects.first()
                convenio = registro_form.cleaned_data["convenio"]
                nivel_dolor = registro_form.cleaned_data["nivel_dolor"]
                cotizacion = calcular_cotizacion(servicio, convenio, nivel_dolor, clinic_info)
                try:
                    with transaction.atomic():
                        paciente, _creado = Paciente.objects.update_or_create(
                            telefono=registro_form.cleaned_data["telefono"],
                            defaults={
                                "nombre": registro_form.cleaned_data["nombre"],
                                "email": registro_form.cleaned_data["email"],
                                "convenio": convenio,
                                "identificador_convenio": registro_form.cleaned_data["identificador_convenio"],
                            },
                        )
                        cita = Cita.objects.create(
                            paciente=paciente,
                            servicio=servicio,
                            convenio=convenio,
                            origen=Cita.Origen.PRESENCIAL,
                            tipo=registro_form.cleaned_data["tipo"],
                            fecha=fecha,
                            hora_inicio=hora_inicio,
                            hora_fin=hora_fin,
                            precio_original=cotizacion["precio_original"],
                            descuento=cotizacion["descuento"],
                            recargo_dolor=cotizacion["recargo_dolor"],
                            precio_final=cotizacion["precio_final"],
                            anticipo_porcentaje_aplicado=cotizacion["anticipo_porcentaje"],
                            anticipo_requerido=cotizacion["anticipo_requerido"],
                            nivel_dolor=nivel_dolor,
                            estado_cita=Cita.EstadoCita.CONFIRMADA,
                            creado_por=request.user,
                        )
                        if solicitud:
                            solicitud.cita_generada = cita
                            solicitud.estado = SolicitudEmergencia.Estado.RESUELTA
                            solicitud.atendido_por = request.user
                            solicitud.save(update_fields=["cita_generada", "estado", "atendido_por"])
                except IntegrityError:
                    messages.error(request, "Ese horario ya no está disponible. Elige otro.")
                else:
                    messages.success(request, "Cita presencial registrada correctamente.")
                    return redirect(f"{reverse('scheduling:panel_agenda')}?fecha={fecha.isoformat()}")

    return render(request, "scheduling/panel_cita_nueva.html", {
        "buscar_form": buscar_form,
        "registro_form": registro_form,
        "servicio": servicio,
        "fecha": fecha,
        "slots": slots,
        "solicitud": solicitud,
    })


@login_required
@permission_required("scheduling.view_solicitudemergencia", raise_exception=True)
def panel_emergencias(request):
    solicitudes = SolicitudEmergencia.objects.select_related("cita_generada").all()
    estado = request.GET.get("estado")
    if estado:
        solicitudes = solicitudes.filter(estado=estado)

    return render(request, "scheduling/panel_emergencias.html", {
        "solicitudes": solicitudes,
        "estados": SolicitudEmergencia.Estado.choices,
        "filtros": request.GET,
    })


@login_required
@permission_required("scheduling.change_solicitudemergencia", raise_exception=True)
def panel_solicitud_cambiar_estado(request, solicitud_id):
    solicitud = get_object_or_404(SolicitudEmergencia, pk=solicitud_id)
    if request.method == "POST":
        form = EstadoSolicitudForm(request.POST)
        if form.is_valid():
            solicitud.estado = form.cleaned_data["estado"]
            solicitud.save(update_fields=["estado"])
            messages.success(request, "Estado de la solicitud actualizado.")
    next_url = request.POST.get("next") or reverse("scheduling:panel_emergencias")
    return redirect(next_url)


@login_required
@permission_required("scheduling.view_cita", raise_exception=True)
def panel_dashboard(request):
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)

    citas_hoy = (
        Cita.objects.filter(fecha=hoy)
        .exclude(estado_cita=Cita.EstadoCita.CANCELADA)
        .select_related("paciente", "servicio")
        .order_by("hora_inicio")
    )
    confirmadas_hoy = citas_hoy.filter(estado_cita=Cita.EstadoCita.CONFIRMADA).count()
    pendientes_hoy = citas_hoy.filter(estado_cita=Cita.EstadoCita.PENDIENTE_CONFIRMACION).count()

    anticipos_mes = Cita.objects.filter(
        created_at__date__gte=inicio_mes, estado_anticipo=Cita.EstadoAnticipo.PAGADO,
    ).aggregate(total=Sum("anticipo_requerido"))["total"] or 0

    citas_proximas = (
        Cita.objects.filter(fecha__gt=hoy)
        .exclude(estado_cita=Cita.EstadoCita.CANCELADA)
        .select_related("paciente", "servicio")
        .order_by("fecha", "hora_inicio")[:8]
    )

    bloqueos_activos = BloqueoAgenda.objects.filter(
        activo=True, fecha_hora_fin__gte=timezone.now()
    ).order_by("fecha_hora_inicio")

    solicitudes_pendientes = SolicitudEmergencia.objects.filter(
        estado=SolicitudEmergencia.Estado.PENDIENTE
    ).count()

    return render(request, "scheduling/panel_dashboard.html", {
        "hoy": hoy,
        "citas_hoy": citas_hoy,
        "citas_proximas": citas_proximas,
        "confirmadas_hoy": confirmadas_hoy,
        "pendientes_hoy": pendientes_hoy,
        "anticipos_mes": anticipos_mes,
        "bloqueos_activos": bloqueos_activos,
        "solicitudes_pendientes": solicitudes_pendientes,
    })


@login_required
@permission_required("scheduling.view_horarioatencion", raise_exception=True)
def panel_disponibilidad(request):
    puede_editar_horario = request.user.has_perm("scheduling.change_horarioatencion")

    if request.method == "POST" and "guardar_horarios" in request.POST:
        if not puede_editar_horario:
            messages.error(request, "No tienes permiso para modificar el horario semanal.")
            return redirect("scheduling:panel_disponibilidad")
        for dia_valor, _ in HorarioAtencion.Dia.choices:
            abierto = request.POST.get(f"abierto_{dia_valor}") == "on"
            hora_inicio = request.POST.get(f"inicio_{dia_valor}")
            hora_fin = request.POST.get(f"fin_{dia_valor}")
            if abierto and hora_inicio and hora_fin:
                HorarioAtencion.objects.update_or_create(
                    dia_semana=dia_valor,
                    defaults={"hora_inicio": hora_inicio, "hora_fin": hora_fin},
                )
            else:
                HorarioAtencion.objects.filter(dia_semana=dia_valor).delete()
        messages.success(request, "Horario semanal actualizado.")
        return redirect("scheduling:panel_disponibilidad")

    form = BloqueoForm()
    if request.method == "POST" and "crear_bloqueo" in request.POST:
        form = BloqueoForm(request.POST)
        if form.is_valid():
            tipo = form.cleaned_data["tipo"]
            if tipo == "dia_completo":
                fecha_hora_inicio = timezone.make_aware(
                    datetime.combine(form.cleaned_data["fecha_inicio"], time.min)
                )
                fecha_fin = form.cleaned_data.get("fecha_fin") or form.cleaned_data["fecha_inicio"]
                fecha_hora_fin = timezone.make_aware(datetime.combine(fecha_fin, time.max))
            else:
                fecha_hora_inicio = timezone.make_aware(
                    datetime.combine(form.cleaned_data["fecha_inicio"], form.cleaned_data["hora_inicio"])
                )
                fecha_hora_fin = timezone.make_aware(
                    datetime.combine(form.cleaned_data["fecha_inicio"], form.cleaned_data["hora_fin"])
                )

            motivo = form.cleaned_data["motivo"]
            bloqueo = BloqueoAgenda.objects.create(
                fecha_hora_inicio=fecha_hora_inicio,
                fecha_hora_fin=fecha_hora_fin,
                motivo=motivo,
                creado_por=request.user,
            )

            # Avisar a los pacientes con anticipación: si el bloqueo se registra
            # con 24 horas o más antes de que comience, se publica un aviso
            # público explicando cuándo no habrá citas y por qué. Bloqueos de
            # último momento (menos de 24h) no generan aviso público — para
            # esos, el aviso a los pacientes ya agendados es la advertencia de
            # arriba, que le corresponde resolver directamente a la secretaria.
            aviso_publicado = False
            if fecha_hora_inicio - timezone.now() >= timedelta(hours=24):
                if tipo == "dia_completo" and fecha_hora_inicio.date() != fecha_hora_fin.date():
                    cuando = (
                        f"del {fecha_hora_inicio:%d/%m/%Y} al {fecha_hora_fin:%d/%m/%Y}"
                    )
                elif tipo == "dia_completo":
                    cuando = f"el {fecha_hora_inicio:%d/%m/%Y}"
                else:
                    cuando = (
                        f"el {fecha_hora_inicio:%d/%m/%Y} de {fecha_hora_inicio:%H:%M} "
                        f"a {fecha_hora_fin:%H:%M}"
                    )

                Aviso.objects.create(
                    titulo="Sin citas disponibles",
                    mensaje=f"No tendremos citas disponibles {cuando}. Motivo: {motivo}.",
                    fecha_inicio_publicacion=timezone.now(),
                    fecha_fin_publicacion=fecha_hora_fin,
                    fecha_evento_inicio=fecha_hora_inicio,
                    fecha_evento_fin=fecha_hora_fin,
                    bloqueo_relacionado=bloqueo,
                    creado_por=request.user,
                )
                aviso_publicado = True

            afectadas = citas_afectadas_por_bloqueo(fecha_hora_inicio, fecha_hora_fin)
            if afectadas:
                nombres = ", ".join(
                    f"{c.paciente.nombre} ({c.fecha:%d/%m} {c.hora_inicio:%H:%M})" for c in afectadas
                )
                messages.warning(
                    request,
                    f"Bloqueo registrado, pero ya había {len(afectadas)} cita(s) en ese rango que "
                    f"necesitan reprogramarse: {nombres}.",
                )
            elif aviso_publicado:
                messages.success(
                    request,
                    "Bloqueo registrado y aviso publicado en la página para los pacientes.",
                )
            else:
                messages.success(
                    request,
                    "Bloqueo registrado correctamente. Como es con menos de 24 horas de "
                    "anticipación, no se publicó aviso público.",
                )
            return redirect("scheduling:panel_disponibilidad")

    horarios_por_dia = {h.dia_semana: h for h in HorarioAtencion.objects.all()}
    dias = [
        {"valor": valor, "nombre": nombre, "horario": horarios_por_dia.get(valor)}
        for valor, nombre in HorarioAtencion.Dia.choices
    ]

    bloqueos = BloqueoAgenda.objects.filter(activo=True).order_by("-fecha_hora_inicio")

    return render(request, "scheduling/panel_disponibilidad.html", {
        "dias": dias,
        "bloqueos": bloqueos,
        "form": form,
        "puede_editar_horario": puede_editar_horario,
    })


@login_required
@permission_required("scheduling.change_bloqueoagenda", raise_exception=True)
def panel_bloqueo_desactivar(request, bloqueo_id):
    bloqueo = get_object_or_404(BloqueoAgenda, pk=bloqueo_id)
    if request.method == "POST":
        bloqueo.activo = False
        bloqueo.save(update_fields=["activo"])
        # El aviso público asociado ya no aplica si el bloqueo se quita.
        bloqueo.avisos.filter(activo=True).update(activo=False)
        messages.success(request, "Bloqueo desactivado. Ese horario vuelve a estar disponible.")
    return redirect("scheduling:panel_disponibilidad")


@login_required
@permission_required("scheduling.view_cita", raise_exception=True)
def panel_buscar_citas(request):
    query = request.GET.get("q", "").strip()
    tiempo = request.GET.get("tiempo", "todas")
    estado = request.GET.get("estado", "")

    citas = Cita.objects.select_related("paciente", "servicio", "convenio").all()

    if query:
        citas = citas.filter(
            Q(paciente__nombre__icontains=query) | Q(paciente__telefono__icontains=query)
        )

    hoy = timezone.localdate()
    if tiempo == "hoy":
        citas = citas.filter(fecha=hoy)
    elif tiempo == "manana":
        citas = citas.filter(fecha=hoy + timedelta(days=1))
    elif tiempo == "semana":
        citas = citas.filter(fecha__gte=hoy, fecha__lte=hoy + timedelta(days=7))
    elif tiempo == "pasadas":
        citas = citas.filter(fecha__lt=hoy)

    if estado:
        citas = citas.filter(estado_cita=estado)

    citas = citas.order_by("-fecha", "hora_inicio")

    paginator = Paginator(citas, 25)
    pagina = paginator.get_page(request.GET.get("pagina"))

    return render(request, "scheduling/panel_buscar_citas.html", {
        "citas": pagina,
        "query": query,
        "tiempo": tiempo,
        "estado": estado,
        "estados": Cita.EstadoCita.choices,
        "estados_anticipo": Cita.EstadoAnticipo.choices,
        "filtros": request.GET,
    })
