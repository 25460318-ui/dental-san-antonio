from django.contrib import admin

from .models import Aviso, BloqueoAgenda, Cita, HorarioAtencion, Paciente, SolicitudEmergencia

admin.site.register(Paciente)
admin.site.register(HorarioAtencion)
admin.site.register(BloqueoAgenda)
admin.site.register(Aviso)
admin.site.register(Cita)
admin.site.register(SolicitudEmergencia)
