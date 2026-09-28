from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from catalog.models import Convenio, Servicio


class SolicitudEmergencia(models.Model):
    """
    Solicitud enviada por un paciente antes de convertirse en una Cita real.
    Todavía no tiene fecha/hora/precio: eso lo define la secretaria al
    contactar al paciente y agendarlo (Cita con tipo=emergencia).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de contacto"
        CONTACTADO = "contactado", "Contactado"
        RESUELTA = "resuelta", "Resuelta"
        DESCARTADA = "descartada", "Descartada"

    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20)
    motivo = models.CharField(max_length=255, help_text="Breve descripción del problema.")
    nivel_dolor = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    cita_generada = models.ForeignKey(
        "Cita", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitud_emergencia_origen",
    )
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitudes_emergencia_atendidas",
    )
    notas_internas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Solicitud de emergencia"
        verbose_name_plural = "Solicitudes de emergencia"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.nombre} — {self.get_estado_display()}"


class Paciente(models.Model):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    convenio = models.ForeignKey(
        Convenio, on_delete=models.SET_NULL, null=True, blank=True, related_name="pacientes"
    )
    identificador_convenio = models.CharField(
        max_length=50, blank=True,
        help_text="Número de trabajador/credencial que respalda su pertenencia al convenio. "
                   "La validación contra la institución la hace el consultorio manualmente.",
    )
    notas = models.TextField(blank=True)

    def __str__(self):
        return self.nombre


class HorarioAtencion(models.Model):
    class Dia(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    dia_semana = models.IntegerField(choices=Dia.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        verbose_name = "Horario de atención"
        verbose_name_plural = "Horarios de atención"
        ordering = ["dia_semana", "hora_inicio"]

    def __str__(self):
        return f"{self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"


class BloqueoAgenda(models.Model):
    fecha_hora_inicio = models.DateTimeField()
    fecha_hora_fin = models.DateTimeField()
    motivo = models.CharField(max_length=255)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bloqueos_creados"
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bloqueo de agenda"
        verbose_name_plural = "Bloqueos de agenda"
        ordering = ["-fecha_hora_inicio"]

    def __str__(self):
        return f"{self.fecha_hora_inicio:%d/%m/%Y %H:%M}-{self.fecha_hora_fin:%H:%M}: {self.motivo}"


class Aviso(models.Model):
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    fecha_inicio_publicacion = models.DateTimeField()
    fecha_fin_publicacion = models.DateTimeField()
    fecha_evento_inicio = models.DateTimeField(null=True, blank=True)
    fecha_evento_fin = models.DateTimeField(null=True, blank=True)
    bloqueo_relacionado = models.ForeignKey(
        BloqueoAgenda, on_delete=models.SET_NULL, null=True, blank=True, related_name="avisos"
    )
    destacado = models.BooleanField(
        default=False, help_text="Si está marcado se muestra como modal; si no, como banner."
    )
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="avisos_creados"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_inicio_publicacion"]

    def __str__(self):
        return self.titulo


class Cita(models.Model):
    class Origen(models.TextChoices):
        ONLINE = "online", "Online"
        PRESENCIAL = "presencial", "Presencial"

    class Tipo(models.TextChoices):
        REGULAR = "regular", "Regular"
        EMERGENCIA = "emergencia", "Emergencia"

    class EstadoCita(models.TextChoices):
        PENDIENTE_CONFIRMACION = "pendiente_confirmacion", "Pendiente de confirmación"
        CONFIRMADA = "confirmada", "Confirmada"
        ATENDIDA = "atendida", "Atendida"
        CANCELADA = "cancelada", "Cancelada"
        NO_ASISTIO = "no_asistio", "No asistió"

    class EstadoAnticipo(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PAGADO = "pagado", "Pagado"
        REEMBOLSADO = "reembolsado", "Reembolsado"
        CANCELADO = "cancelado", "Cancelado"

    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="citas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="citas")
    convenio = models.ForeignKey(
        Convenio, on_delete=models.SET_NULL, null=True, blank=True, related_name="citas"
    )
    origen = models.CharField(max_length=20, choices=Origen.choices)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.REGULAR)

    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    # Fotografía de las condiciones económicas al momento de reservar.
    # precio_final = precio_original - descuento + recargo_dolor
    precio_original = models.DecimalField(max_digits=8, decimal_places=2)
    descuento = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    recargo_dolor = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Cargo extra aplicado si el nivel de dolor reportado alcanzó el umbral configurado.",
    )
    precio_final = models.DecimalField(max_digits=8, decimal_places=2)
    anticipo_porcentaje_aplicado = models.DecimalField(max_digits=5, decimal_places=2)
    anticipo_requerido = models.DecimalField(max_digits=8, decimal_places=2)

    estado_cita = models.CharField(
        max_length=30, choices=EstadoCita.choices, default=EstadoCita.PENDIENTE_CONFIRMACION
    )
    estado_anticipo = models.CharField(
        max_length=20, choices=EstadoAnticipo.choices, default=EstadoAnticipo.PENDIENTE
    )

    nivel_dolor = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    notas = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="citas_creadas",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cita"
        verbose_name_plural = "Citas"
        ordering = ["fecha", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["fecha", "hora_inicio"],
                condition=~models.Q(estado_cita="cancelada"),
                name="unique_cita_activa_por_horario",
            )
        ]

    def __str__(self):
        return f"{self.paciente} - {self.servicio} - {self.fecha} {self.hora_inicio}"
