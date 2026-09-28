from django.contrib.auth.models import Group, User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ClinicInfo(models.Model):
    """Singleton con los datos del consultorio, editables desde el admin."""

    nombre = models.CharField(max_length=150, default="Dental San Antonio")
    direccion = models.CharField(max_length=255)
    telefono_1 = models.CharField(max_length=20)
    telefono_2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField()
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    anticipo_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    reservas_online_activas = models.BooleanField(default=True)
    mensaje_hero = models.CharField(
        max_length=255, blank=True,
        help_text="Mensaje corto del hero (puede ser un placeholder temporal).",
    )
    dolor_umbral_recargo = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Nivel de dolor (0-10) a partir del cual se aplica el cargo extra.",
    )
    dolor_recargo_monto = models.DecimalField(
        max_digits=8, decimal_places=2, default=100,
        help_text="Monto fijo que se suma al precio cuando el dolor reportado alcanza el umbral.",
    )

    class Meta:
        verbose_name = "Información del consultorio"
        verbose_name_plural = "Información del consultorio"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass


class StaffProfile(models.Model):
    class Rol(models.TextChoices):
        DOCTOR = "doctor", "Doctor"
        SECRETARIA = "secretaria", "Secretaria"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    rol = models.CharField(max_length=20, choices=Rol.choices)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_rol_display()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        secretaria_group, _ = Group.objects.get_or_create(name="Secretaria")
        if self.rol == self.Rol.DOCTOR:
            self.user.groups.add(doctor_group)
            self.user.groups.remove(secretaria_group)
        else:
            self.user.groups.add(secretaria_group)
            self.user.groups.remove(doctor_group)
