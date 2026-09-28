from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("asistencia/responder/", views.asistencia_responder, name="asistencia_responder"),
]
