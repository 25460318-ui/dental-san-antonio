from django.http import JsonResponse
from django.shortcuts import render

from catalog.models import CategoriaServicio, Convenio

from .asistencia import detectar_intent, responder


def home(request):
    convenios = Convenio.objects.filter(activo=True)
    categorias = CategoriaServicio.objects.filter(servicios__activo=True).distinct()
    context = {
        "convenios": convenios,
        "categorias": categorias,
    }
    return render(request, "core/home.html", context)


def asistencia_responder(request):
    intent = request.GET.get("intent")
    if not intent:
        texto = request.GET.get("q", "")
        intent = detectar_intent(texto)
    return JsonResponse(responder(intent))
