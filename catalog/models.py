from django.db import models


class CategoriaServicio(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion_corta = models.CharField(max_length=255, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Categoría de servicio"
        verbose_name_plural = "Categorías de servicio"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    categoria = models.ForeignKey(CategoriaServicio, on_delete=models.PROTECT, related_name="servicios")
    nombre = models.CharField(max_length=150)
    descripcion_breve = models.CharField(max_length=255, blank=True)
    precio_general = models.DecimalField(max_digits=8, decimal_places=2)
    duracion_minutos = models.PositiveIntegerField(null=True, blank=True)
    destacado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ["categoria__orden", "orden", "nombre"]

    def __str__(self):
        return self.nombre


class Convenio(models.Model):
    nombre = models.CharField(max_length=100)
    logo = models.ImageField(upload_to="convenios/", blank=True, null=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Convenio"
        verbose_name_plural = "Convenios"

    def __str__(self):
        return self.nombre


class PrecioConvenio(models.Model):
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name="precios_convenio")
    convenio = models.ForeignKey(Convenio, on_delete=models.CASCADE, related_name="precios")
    precio_especial = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Precio con convenio"
        verbose_name_plural = "Precios con convenio"
        unique_together = ("servicio", "convenio")

    def __str__(self):
        return f"{self.servicio} - {self.convenio}: ${self.precio_especial}"
