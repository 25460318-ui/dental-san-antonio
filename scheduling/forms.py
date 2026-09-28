from django import forms
from django.utils import timezone

from catalog.models import CategoriaServicio, Convenio, Servicio

from .models import Cita, SolicitudEmergencia


class CategoriaForm(forms.Form):
    categoria = forms.ModelChoiceField(
        queryset=CategoriaServicio.objects.filter(servicios__activo=True).distinct(),
        label="¿Qué tipo de servicio necesitas?",
    )


class ServicioForm(forms.Form):
    servicio = forms.ModelChoiceField(
        queryset=Servicio.objects.none(),
        label="¿Cuál de estos servicios?",
        empty_label=None,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, categoria=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Servicio.objects.filter(activo=True)
        if categoria:
            qs = qs.filter(categoria=categoria)
        self.fields["servicio"].queryset = qs.order_by("orden", "nombre")


class FechaForm(forms.Form):
    fecha = forms.DateField(
        label="¿Qué día te gustaría venir?",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        if fecha < timezone.localdate():
            raise forms.ValidationError("Elige una fecha a partir de hoy.")
        return fecha


class HorarioForm(forms.Form):
    horario = forms.ChoiceField(label="Horarios disponibles", widget=forms.RadioSelect)

    def __init__(self, *args, choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["horario"].choices = choices or []


class DatosPacienteForm(forms.Form):
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    telefono = forms.CharField(label="Teléfono", max_length=20)
    email = forms.EmailField(label="Correo (opcional)", required=False)


class ConvenioForm(forms.Form):
    convenio = forms.ModelChoiceField(
        queryset=Convenio.objects.filter(activo=True),
        label="¿Perteneces a alguna institución con convenio?",
        required=False,
        empty_label="No pertenezco a ningún convenio",
    )
    identificador_convenio = forms.CharField(
        label="Número de trabajador / credencial (si aplica)",
        max_length=50,
        required=False,
        help_text="Lo verificaremos contigo antes de tu cita.",
    )


class DolorForm(forms.Form):
    nivel_dolor = forms.IntegerField(
        label="¿Qué tanto dolor sientes ahora mismo?",
        min_value=0,
        max_value=10,
        initial=0,
        widget=forms.NumberInput(attrs={"type": "range", "min": 0, "max": 10, "step": 1}),
    )


class ServicioFechaForm(forms.Form):
    """Usada por el panel para buscar horarios: servicio + fecha en un solo paso."""

    servicio = forms.ModelChoiceField(
        queryset=Servicio.objects.filter(activo=True).select_related("categoria"),
        label="Servicio",
    )
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))


class RegistroPresencialForm(forms.Form):
    """Datos del paciente para una cita registrada por el personal del consultorio."""

    nombre = forms.CharField(label="Nombre completo", max_length=150)
    telefono = forms.CharField(label="Teléfono", max_length=20)
    email = forms.EmailField(label="Correo (opcional)", required=False)
    convenio = forms.ModelChoiceField(
        queryset=Convenio.objects.filter(activo=True),
        label="Convenio",
        required=False,
        empty_label="Sin convenio",
    )
    identificador_convenio = forms.CharField(
        label="Número de trabajador / credencial", max_length=50, required=False,
    )
    nivel_dolor = forms.IntegerField(
        label="Nivel de dolor (opcional)", min_value=0, max_value=10, required=False,
    )
    tipo = forms.ChoiceField(label="Tipo de cita", choices=Cita.Tipo.choices, initial=Cita.Tipo.REGULAR)


class EstadoCitaForm(forms.Form):
    estado_cita = forms.ChoiceField(choices=Cita.EstadoCita.choices, label="Estado")


class EstadoAnticipoForm(forms.Form):
    estado_anticipo = forms.ChoiceField(choices=Cita.EstadoAnticipo.choices, label="Anticipo")


class BloqueoForm(forms.Form):
    TIPO_CHOICES = [
        ("dia_completo", "Día(s) completo(s) — vacaciones, festivo, etc."),
        ("horario", "Rango de horas en un solo día"),
    ]

    tipo = forms.ChoiceField(choices=TIPO_CHOICES, label="Tipo de bloqueo", initial="horario")
    motivo = forms.CharField(label="Motivo", max_length=255)
    fecha_inicio = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    fecha_fin = forms.DateField(
        label="Fecha de fin (solo para día completo, opcional)",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    hora_inicio = forms.TimeField(
        label="Hora de inicio", widget=forms.TimeInput(attrs={"type": "time"}), required=False,
    )
    hora_fin = forms.TimeField(
        label="Hora de fin", widget=forms.TimeInput(attrs={"type": "time"}), required=False,
    )

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        fecha_inicio = cleaned.get("fecha_inicio")
        fecha_fin = cleaned.get("fecha_fin")
        hora_inicio = cleaned.get("hora_inicio")
        hora_fin = cleaned.get("hora_fin")

        if tipo == "horario":
            if not hora_inicio or not hora_fin:
                raise forms.ValidationError("Indica la hora de inicio y de fin del bloqueo.")
            if hora_fin <= hora_inicio:
                raise forms.ValidationError("La hora de fin debe ser posterior a la hora de inicio.")
        elif tipo == "dia_completo" and fecha_fin and fecha_fin < fecha_inicio:
            raise forms.ValidationError("La fecha de fin no puede ser anterior a la fecha de inicio.")
        return cleaned


class EmergenciaForm(forms.Form):
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    telefono = forms.CharField(label="Teléfono de contacto", max_length=20)
    motivo = forms.CharField(
        label="Cuéntanos brevemente qué te pasa",
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    nivel_dolor = forms.IntegerField(
        label="¿Qué tanto dolor sientes ahora mismo?",
        min_value=0,
        max_value=10,
        initial=5,
        widget=forms.NumberInput(attrs={"type": "range", "min": 0, "max": 10, "step": 1}),
    )


class EstadoSolicitudForm(forms.Form):
    estado = forms.ChoiceField(choices=SolicitudEmergencia.Estado.choices, label="Estado")
