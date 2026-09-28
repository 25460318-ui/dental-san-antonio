from django.contrib import admin

from .models import CategoriaServicio, Convenio, PrecioConvenio, Servicio

admin.site.register(CategoriaServicio)
admin.site.register(Servicio)
admin.site.register(Convenio)
admin.site.register(PrecioConvenio)
