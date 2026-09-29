from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import CategoriaServicio, Convenio, PrecioConvenio, Servicio
from core.models import ClinicInfo, StaffProfile

from .models import BloqueoAgenda, Cita, HorarioAtencion, Paciente, SolicitudEmergencia
from .services import calcular_cotizacion, franjas_disponibles, hay_conflicto


def _proximo_lunes():
    """Un lunes real en el futuro, sin importar qué día sea 'hoy' al correr las pruebas."""
    hoy = timezone.localdate()
    dias = (7 - hoy.weekday()) % 7 or 7
    return hoy + timedelta(days=dias)


def _crear_catalogo_basico():
    categoria = CategoriaServicio.objects.create(nombre="Servicios generales", orden=1)
    servicio = Servicio.objects.create(
        categoria=categoria, nombre="Limpieza", precio_general=Decimal("700"),
        activo=True, duracion_minutos=30,
    )
    convenio = Convenio.objects.create(nombre="SUTUC", activo=True)
    PrecioConvenio.objects.create(servicio=servicio, convenio=convenio, precio_especial=Decimal("550"))
    return categoria, servicio, convenio


def _crear_clinic_info(**overrides):
    # ClinicInfo es un singleton (pk=1 forzado) ya sembrado por una
    # migración de datos, así que aquí solo lo actualizamos con valores
    # conocidos para la prueba en vez de intentar crear uno nuevo.
    datos = dict(
        nombre="Dental San Antonio",
        direccion="Tekuan 100, Villa Izcalli, Villa de Álvarez, Colima.",
        telefono_1="3123966831",
        email="sanantoniodental4@gmail.com",
        anticipo_porcentaje=Decimal("50"),
        dolor_umbral_recargo=8,
        dolor_recargo_monto=Decimal("100"),
    )
    datos.update(overrides)
    clinic_info, _creado = ClinicInfo.objects.update_or_create(pk=1, defaults=datos)
    return clinic_info


class DisponibilidadTests(TestCase):
    """El motor de disponibilidad (services.py) es lo más crítico del proyecto:
    nunca debe permitir que dos citas se encimen."""

    def setUp(self):
        self.categoria, self.servicio, self.convenio = _crear_catalogo_basico()
        _crear_clinic_info()
        self.lunes = date(2026, 9, 28)
        assert self.lunes.weekday() == 0
        HorarioAtencion.objects.create(dia_semana=0, hora_inicio=time(9, 0), hora_fin=time(18, 0))
        self.user = User.objects.create_user("doctor_disp", password="x")
        self.paciente = Paciente.objects.create(nombre="Juan Pérez", telefono="3120000000")

    def _crear_cita(self, hora_inicio, hora_fin, **overrides):
        datos = dict(
            paciente=self.paciente, servicio=self.servicio, origen=Cita.Origen.PRESENCIAL,
            fecha=self.lunes, hora_inicio=hora_inicio, hora_fin=hora_fin,
            precio_original=Decimal("700"), precio_final=Decimal("700"),
            anticipo_porcentaje_aplicado=Decimal("50"), anticipo_requerido=Decimal("350"),
            creado_por=self.user,
        )
        datos.update(overrides)
        return Cita.objects.create(**datos)

    def test_horario_libre_sin_citas(self):
        self.assertFalse(hay_conflicto(self.lunes, time(10, 0), time(10, 30)))

    def test_detecta_solapamiento_parcial(self):
        self._crear_cita(time(10, 0), time(11, 0))
        self.assertTrue(hay_conflicto(self.lunes, time(10, 30), time(11, 30)))

    def test_permite_horario_justo_despues(self):
        self._crear_cita(time(10, 0), time(11, 0))
        self.assertFalse(hay_conflicto(self.lunes, time(11, 0), time(12, 0)))

    def test_cita_cancelada_no_bloquea(self):
        self._crear_cita(time(10, 0), time(11, 0), estado_cita=Cita.EstadoCita.CANCELADA)
        self.assertFalse(hay_conflicto(self.lunes, time(10, 0), time(11, 0)))

    def test_bloqueo_de_agenda_impide_reserva(self):
        BloqueoAgenda.objects.create(
            fecha_hora_inicio=timezone.make_aware(datetime.combine(self.lunes, time(14, 0))),
            fecha_hora_fin=timezone.make_aware(datetime.combine(self.lunes, time(16, 0))),
            motivo="Prueba", creado_por=self.user,
        )
        self.assertTrue(hay_conflicto(self.lunes, time(14, 30), time(15, 0)))
        self.assertFalse(hay_conflicto(self.lunes, time(16, 0), time(17, 0)))

    def test_bloqueo_inactivo_no_afecta(self):
        BloqueoAgenda.objects.create(
            fecha_hora_inicio=timezone.make_aware(datetime.combine(self.lunes, time(14, 0))),
            fecha_hora_fin=timezone.make_aware(datetime.combine(self.lunes, time(16, 0))),
            motivo="Prueba", creado_por=self.user, activo=False,
        )
        self.assertFalse(hay_conflicto(self.lunes, time(14, 30), time(15, 0)))

    def test_franjas_disponibles_excluye_ocupadas(self):
        self._crear_cita(time(10, 0), time(10, 30))
        slots = franjas_disponibles(self.lunes, duracion_minutos=30)
        inicios = [s[0] for s in slots]
        self.assertNotIn(time(10, 0), inicios)
        self.assertIn(time(10, 30), inicios)

    def test_unique_constraint_evita_doble_reserva_exacta(self):
        self._crear_cita(time(10, 0), time(10, 30))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._crear_cita(time(10, 0), time(10, 30))


class CotizacionTests(TestCase):
    """calcular_cotizacion decide cuánto se le cobra a cada paciente — tiene
    que ser exacto: precio, descuento por convenio y recargo por dolor."""

    def setUp(self):
        _, self.servicio, self.convenio = _crear_catalogo_basico()
        self.clinic_info = _crear_clinic_info()

    def test_precio_general_sin_convenio(self):
        r = calcular_cotizacion(self.servicio, None, 0, self.clinic_info)
        self.assertEqual(r["precio_final"], Decimal("700"))
        self.assertEqual(r["descuento"], Decimal("0"))
        self.assertEqual(r["anticipo_requerido"], Decimal("350.00"))

    def test_precio_con_convenio(self):
        r = calcular_cotizacion(self.servicio, self.convenio, 0, self.clinic_info)
        self.assertEqual(r["precio_final"], Decimal("550"))
        self.assertEqual(r["descuento"], Decimal("150"))

    def test_recargo_por_dolor_en_el_umbral(self):
        r = calcular_cotizacion(self.servicio, None, 8, self.clinic_info)
        self.assertEqual(r["recargo_dolor"], Decimal("100"))
        self.assertEqual(r["precio_final"], Decimal("800"))

    def test_sin_recargo_debajo_del_umbral(self):
        r = calcular_cotizacion(self.servicio, None, 7, self.clinic_info)
        self.assertEqual(r["recargo_dolor"], Decimal("0"))

    def test_convenio_y_dolor_alto_combinados(self):
        r = calcular_cotizacion(self.servicio, self.convenio, 9, self.clinic_info)
        self.assertEqual(r["precio_final"], Decimal("650"))  # 700 - 150 + 100


class StaffProfileTests(TestCase):
    def test_crear_staff_profile_marca_is_staff(self):
        user = User.objects.create_user("nuevo_staff", password="x")
        self.assertFalse(user.is_staff)
        StaffProfile.objects.create(user=user, rol=StaffProfile.Rol.SECRETARIA)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)


class PermisosPanelTests(TestCase):
    def setUp(self):
        _crear_catalogo_basico()
        _crear_clinic_info()
        HorarioAtencion.objects.create(dia_semana=0, hora_inicio=time(9, 0), hora_fin=time(18, 0))

        self.doctor = User.objects.create_user("doctor_perm", password="x")
        StaffProfile.objects.create(user=self.doctor, rol=StaffProfile.Rol.DOCTOR)

        self.secretaria = User.objects.create_user("secretaria_perm", password="x")
        StaffProfile.objects.create(user=self.secretaria, rol=StaffProfile.Rol.SECRETARIA)

    def test_usuario_sin_iniciar_sesion_es_redirigido_a_login(self):
        resp = self.client.get(reverse("scheduling:panel_agenda"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/panel/accounts/login/", resp.url)

    def test_secretaria_no_puede_cambiar_el_horario_semanal(self):
        self.client.force_login(self.secretaria)
        self.client.post(reverse("scheduling:panel_disponibilidad"), {
            "guardar_horarios": "1", "abierto_0": "on", "inicio_0": "10:00", "fin_0": "12:00",
        })
        h = HorarioAtencion.objects.get(dia_semana=0)
        self.assertEqual(h.hora_inicio, time(9, 0))  # sin cambios

    def test_doctor_si_puede_cambiar_el_horario_semanal(self):
        self.client.force_login(self.doctor)
        self.client.post(reverse("scheduling:panel_disponibilidad"), {
            "guardar_horarios": "1", "abierto_0": "on", "inicio_0": "10:00", "fin_0": "12:00",
        })
        h = HorarioAtencion.objects.get(dia_semana=0)
        self.assertEqual(h.hora_inicio, time(10, 0))

    def test_usuario_sin_rol_no_accede_al_panel(self):
        sin_rol = User.objects.create_user("sin_rol", password="x")
        self.client.force_login(sin_rol)
        resp = self.client.get(reverse("scheduling:panel_emergencias"))
        self.assertEqual(resp.status_code, 403)


class ReservaWizardTests(TestCase):
    """El flujo completo de reserva en línea, de principio a fin."""

    def setUp(self):
        self.categoria, self.servicio, self.convenio = _crear_catalogo_basico()
        _crear_clinic_info()
        self.lunes = _proximo_lunes()
        HorarioAtencion.objects.create(
            dia_semana=self.lunes.weekday(), hora_inicio=time(9, 0), hora_fin=time(18, 0)
        )

    def _avanzar_hasta_resumen(self, sitio_web=""):
        c = self.client
        c.get(reverse("scheduling:reservar_categoria") + f"?categoria={self.categoria.pk}")
        c.post(reverse("scheduling:reservar_servicio"), {"servicio": self.servicio.pk})
        c.post(reverse("scheduling:reservar_fecha"), {"fecha": self.lunes.isoformat()})
        c.post(reverse("scheduling:reservar_horario"), {"horario": "09:00:00|09:30:00"})
        c.post(reverse("scheduling:reservar_datos"), {
            "nombre": "Paciente Test", "telefono": "3121234567", "email": "",
            "sitio_web": sitio_web,
        })
        c.post(reverse("scheduling:reservar_convenio"), {"convenio": "", "identificador_convenio": ""})
        c.post(reverse("scheduling:reservar_dolor"), {"nivel_dolor": 0})

    def test_flujo_completo_crea_la_cita_correctamente(self):
        self._avanzar_hasta_resumen()
        resp = self.client.post(reverse("scheduling:reservar_resumen"))
        self.assertEqual(Cita.objects.count(), 1)
        cita = Cita.objects.first()
        self.assertEqual(cita.servicio, self.servicio)
        self.assertEqual(cita.precio_final, Decimal("700.00"))
        self.assertEqual(cita.estado_cita, Cita.EstadoCita.PENDIENTE_CONFIRMACION)
        self.assertRedirects(resp, reverse("scheduling:reserva_confirmacion"))

    def test_resumen_rechaza_si_alguien_mas_tomo_el_horario_primero(self):
        self._avanzar_hasta_resumen()
        # Alguien más (ej. la secretaria, presencial) se adelanta justo antes de confirmar.
        otro = Paciente.objects.create(nombre="Otro Paciente", telefono="3110000000")
        staff = User.objects.create_user("secre_race", password="x")
        Cita.objects.create(
            paciente=otro, servicio=self.servicio, origen=Cita.Origen.PRESENCIAL,
            fecha=self.lunes, hora_inicio=time(9, 0), hora_fin=time(9, 30),
            precio_original=Decimal("700"), precio_final=Decimal("700"),
            anticipo_porcentaje_aplicado=Decimal("50"), anticipo_requerido=Decimal("350"),
            creado_por=staff,
        )
        resp = self.client.post(reverse("scheduling:reservar_resumen"))
        self.assertEqual(Cita.objects.count(), 1)  # solo la de "Otro Paciente"
        self.assertRedirects(resp, reverse("scheduling:reservar_horario"))

    def test_honeypot_impide_que_se_cree_la_cita(self):
        self._avanzar_hasta_resumen(sitio_web="http://spam-bot.example")
        self.client.post(reverse("scheduling:reservar_resumen"))
        self.assertEqual(Cita.objects.count(), 0)
        self.assertEqual(Paciente.objects.count(), 0)


class EmergenciaTests(TestCase):
    def setUp(self):
        self.clinic_info = _crear_clinic_info()

    def test_solicitud_valida_se_guarda_y_avisa_al_consultorio(self):
        resp = self.client.post(reverse("scheduling:emergencia_formulario"), {
            "nombre": "Ana", "telefono": "3121112222",
            "motivo": "Dolor muy fuerte", "nivel_dolor": 9, "sitio_web": "",
        })
        self.assertEqual(SolicitudEmergencia.objects.count(), 1)
        self.assertRedirects(resp, reverse("scheduling:emergencia_confirmacion"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.clinic_info.email, mail.outbox[0].to)

    def test_honeypot_no_guarda_la_solicitud_pero_parece_exitoso(self):
        resp = self.client.post(reverse("scheduling:emergencia_formulario"), {
            "nombre": "Bot", "telefono": "0000000000",
            "motivo": "spam", "nivel_dolor": 5, "sitio_web": "http://spam-bot.example",
        })
        self.assertEqual(SolicitudEmergencia.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertRedirects(resp, reverse("scheduling:emergencia_confirmacion"))


class AnticipoTests(TestCase):
    def setUp(self):
        self.categoria, self.servicio, self.convenio = _crear_catalogo_basico()
        _crear_clinic_info()
        self.secretaria = User.objects.create_user("secre_anticipo", password="x")
        StaffProfile.objects.create(user=self.secretaria, rol=StaffProfile.Rol.SECRETARIA)
        self.paciente = Paciente.objects.create(
            nombre="Pedro", telefono="3123334444", email="pedro@example.com",
        )
        self.cita = Cita.objects.create(
            paciente=self.paciente, servicio=self.servicio, origen=Cita.Origen.ONLINE,
            fecha=timezone.localdate(), hora_inicio=time(9, 0), hora_fin=time(9, 30),
            precio_original=Decimal("700"), precio_final=Decimal("700"),
            anticipo_porcentaje_aplicado=Decimal("50"), anticipo_requerido=Decimal("350"),
            estado_cita=Cita.EstadoCita.PENDIENTE_CONFIRMACION,
        )

    def test_marcar_pagado_confirma_la_cita_y_avisa_al_paciente(self):
        self.client.force_login(self.secretaria)
        self.client.post(
            reverse("scheduling:panel_cambiar_estado_anticipo", args=[self.cita.pk]),
            {"estado_anticipo": "pagado"},
        )
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado_cita, Cita.EstadoCita.CONFIRMADA)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("pedro@example.com", mail.outbox[0].to)

    def test_emergencia_pagada_tambien_avisa_al_consultorio(self):
        self.cita.tipo = Cita.Tipo.EMERGENCIA
        self.cita.save(update_fields=["tipo"])
        self.client.force_login(self.secretaria)
        self.client.post(
            reverse("scheduling:panel_cambiar_estado_anticipo", args=[self.cita.pk]),
            {"estado_anticipo": "pagado"},
        )
        # correo al paciente + alerta al consultorio
        self.assertEqual(len(mail.outbox), 2)
