import unicodedata

from django.urls import reverse

from catalog.models import CategoriaServicio, Convenio, Servicio

from .models import ClinicInfo

# Preguntas frecuentes que ofrecemos como respuesta rápida (botones). El
# asistente NO usa IA todavía —a propósito, según se definió desde el inicio
# del proyecto—, así que solo responde estas preguntas concretas con datos
# reales de la base de datos. Nunca da diagnósticos ni sustituye al doctor.
PREGUNTAS_RAPIDAS = [
    ("agendar", "¿Cómo agendo una cita?"),
    ("servicios", "¿Qué servicios ofrecen?"),
    ("precio_limpieza", "¿Cuánto cuesta una limpieza?"),
    ("anticipo", "¿Qué anticipo necesito?"),
    ("ubicacion", "¿Dónde están ubicados?"),
    ("telefono", "¿Cuál es el teléfono?"),
    ("emergencia", "Tengo una emergencia"),
    ("convenios", "¿Qué convenios tienen?"),
]

_PALABRAS_CLAVE = {
    "agendar": ["agendar", "cita", "reservar", "apartar"],
    "servicios": ["servicio", "tratamiento", "que hacen", "que ofrecen"],
    "precio_limpieza": ["limpieza"],
    "anticipo": ["anticipo", "adelanto", "pago", "abono"],
    "ubicacion": ["ubicacion", "direccion", "donde estan", "como llego", "donde queda"],
    "telefono": ["telefono", "numero", "llamar", "contacto"],
    "emergencia": ["emergencia", "urgencia", "dolor fuerte", "duele mucho", "urgente"],
    "convenios": ["convenio", "sindicato", "sutuc", "snte", "descuento"],
}


def _sin_acentos(texto):
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def detectar_intent(texto):
    normalizado = _sin_acentos(texto.lower())
    for clave, palabras in _PALABRAS_CLAVE.items():
        if any(_sin_acentos(p) in normalizado for p in palabras):
            return clave
    return None


def responder(intent):
    clinic_info = ClinicInfo.objects.first()

    if intent == "agendar":
        return {
            "texto": (
                "Puedes agendar tu cita en línea cuando quieras: eliges la categoría, luego el "
                "servicio, la fecha y el horario que prefieras. Al final te decimos el anticipo "
                "que se necesita para confirmarla."
            ),
            "enlace_texto": "Agendar cita",
            "enlace_url": reverse("scheduling:reservar_categoria"),
        }

    if intent == "servicios":
        categorias = list(CategoriaServicio.objects.filter(servicios__activo=True).distinct())
        if categorias:
            nombres = ", ".join(c.nombre for c in categorias)
            texto = f"Ofrecemos: {nombres}. Los precios de cada servicio los ves al elegir la categoría."
        else:
            texto = "Muy pronto vamos a tener el catálogo de servicios disponible aquí."
        return {"texto": texto, "enlace_texto": "Ver servicios", "enlace_url": reverse("core:home") + "#servicios"}

    if intent == "precio_limpieza":
        servicio = (
            Servicio.objects.filter(nombre__icontains="limpieza", activo=True)
            .exclude(nombre__icontains="profunda")
            .first()
        )
        if servicio:
            texto = (
                f"La {servicio.nombre.lower()} cuesta ${servicio.precio_general:.0f} MXN "
                "(precio general). Si perteneces a un convenio puede haber un precio especial."
            )
        else:
            texto = "No tengo ese precio a la mano en este momento. Llámanos y te decimos al instante."
        return {"texto": texto, "enlace_texto": None, "enlace_url": None}

    if intent == "anticipo":
        porcentaje = clinic_info.anticipo_porcentaje if clinic_info else 50
        return {
            "texto": f"Para confirmar tu cita se requiere un anticipo del {porcentaje:.0f}% del costo del servicio.",
            "enlace_texto": None,
            "enlace_url": None,
        }

    if intent == "ubicacion":
        direccion = clinic_info.direccion if clinic_info else "consulta nuestra dirección en la página"
        return {
            "texto": f"Estamos en: {direccion}".rstrip(".") + ".",
            "enlace_texto": "Ver mapa",
            "enlace_url": reverse("core:home") + "#ubicacion",
        }

    if intent == "telefono":
        if clinic_info:
            telefonos = ", ".join(t for t in [clinic_info.telefono_1, clinic_info.telefono_2] if t)
            texto = f"Puedes llamarnos o mandarnos mensaje al {telefonos}."
        else:
            texto = "Encuentras nuestro teléfono en la parte de contacto de la página."
        return {"texto": texto, "enlace_texto": None, "enlace_url": None}

    if intent == "emergencia":
        telefono = clinic_info.telefono_1 if clinic_info else ""
        return {
            "texto": (
                f"Si es una emergencia, lo más rápido es llamarnos directo al {telefono}. "
                "También puedes enviarnos tu caso desde el botón de Emergencia y te contactamos "
                "lo antes posible. Yo no puedo diagnosticar tu molestia — eso lo revisa el doctor."
            ),
            "enlace_texto": "Ir a Emergencias",
            "enlace_url": reverse("scheduling:emergencia_formulario"),
        }

    if intent == "convenios":
        convenios = list(Convenio.objects.filter(activo=True))
        if convenios:
            nombres = ", ".join(c.nombre for c in convenios)
            texto = (
                f"Tenemos convenio con: {nombres}. Al agendar tu cita puedes indicar si "
                "perteneces a alguno para ver tu precio especial."
            )
        else:
            texto = "Por ahora no tenemos convenios activos registrados."
        return {"texto": texto, "enlace_texto": None, "enlace_url": None}

    telefono = clinic_info.telefono_1 if clinic_info else ""
    return {
        "texto": (
            "No tengo información exacta sobre eso todavía. Para dudas específicas o si sientes "
            f"alguna molestia, lo mejor es llamarnos al {telefono} — yo no puedo dar diagnósticos, "
            "solo el doctor."
        ),
        "enlace_texto": None,
        "enlace_url": None,
    }
