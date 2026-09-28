from decimal import Decimal

from django.db import migrations

CONVENIOS = ["SUTUC", "SNTE Sección 6"]

CATEGORIAS = [
    ("Servicios generales", 1),
    ("Restauraciones y estética", 2),
    ("Prótesis", 3),
    ("Especialidades", 4),
    ("Urgencias", 5),
    ("Odontopediatría", 6),
    ("Aparatología", 7),
]

# (categoria, nombre, precio_general, precio_convenio o None, destacado, descripcion_breve)
SERVICIOS = [
    ("Servicios generales", "Consulta de Diagnóstico y Rx", "400", None, True, ""),
    ("Servicios generales", "Limpieza", "700", "550", True, ""),
    ("Servicios generales", "Limpieza profunda", "900", "700", False, ""),
    ("Servicios generales", "Curetajes", "450", "350", False, ""),
    ("Servicios generales", "Extracción", "850", "700", True, ""),
    ("Servicios generales", "Unidad provisional", "150", "100", False, ""),

    ("Restauraciones y estética", "Resina", "950", "750", True, ""),
    ("Restauraciones y estética", "Reconstrucción estética de Resina", "1500", "1200", False, ""),
    ("Restauraciones y estética", "Incrustación Estética", "1850", "1500", False, ""),
    ("Restauraciones y estética", "Corona de metal porcelana", "2600", "2200", False, ""),
    ("Restauraciones y estética", "Corona estética (E-Max)", "6000", "5000", False, ""),
    ("Restauraciones y estética", "Corona estética Zirconia", "6500", "5500", True, ""),
    ("Restauraciones y estética", "Blanqueamiento", "2200", "1850", False, ""),

    ("Prótesis", "Retiro de Puentes", "500", "300", False, ""),
    ("Prótesis", "Puentes removibles Bilateral Metal Acrílico", "9500", "8000", True, ""),
    (
        "Prótesis",
        "Placas totales con dientes de resina",
        "10150",
        "8150",
        False,
        "Incluye cepillo, caja y adhesivo.",
    ),

    ("Especialidades", "Endodoncia", "3250", "2900", True, ""),
    ("Especialidades", "Endoposte", "1100", "950", False, ""),
    ("Especialidades", "Cirugía de 3er Molar", "2500", "2200", False, ""),
    ("Especialidades", "Desprogramador", "2500", "2200", False, ""),
    ("Especialidades", "Implantes", "27600", "26000", True, ""),
    ("Especialidades", "Guarda oclusal", "1200", "900", False, ""),
    ("Especialidades", "Alambre Muerto", "1500", "1200", False, ""),
    ("Especialidades", "Retiro de Brackets + Limpieza", "1200", None, False, ""),
    ("Especialidades", "Pre Finisher", "4000", "3500", False, ""),
    ("Especialidades", "Cirugía de Frenillo", "2200", "2000", False, ""),
    (
        "Especialidades",
        "Brackets",
        "5700",
        "4700",
        False,
        "Anticipo de tratamiento de ortodoncia. La mensualidad y el plan de pagos se definen en consulta.",
    ),

    ("Urgencias", "Consulta de Emergencia", "800", "500", True, ""),

    ("Odontopediatría", "Diagnóstico, limpieza y aplicación de flúor", "700", "500", True, ""),
    ("Odontopediatría", "Sellador de fosetas y fisuras (por diente)", "750", "650", False, ""),
    (
        "Odontopediatría",
        "Terapias pulpares (pulpotomías y pulpectomías)",
        "1700",
        "1500",
        False,
        "",
    ),
    ("Odontopediatría", "Retratamiento de terapias pulpares", "1400", "1200", False, ""),
    ("Odontopediatría", "Extracciones infantiles", "850", "700", False, ""),
    ("Odontopediatría", "Resinas infantiles", "950", "750", False, ""),
    ("Odontopediatría", "Corona de resina (infantil)", "1650", "1450", False, ""),
    ("Odontopediatría", "Coronas de acero cromo", "1500", "1300", False, ""),
    (
        "Odontopediatría",
        "Aplicación de flúor sistemático",
        "2760",
        "2400",
        False,
        "2 semanas, 6 aplicaciones.",
    ),

    ("Aparatología", "Cita de revisión y seguimiento mensual", "550", "400", True, ""),
    ("Aparatología", "Trampa lingual o de dedo", "2400", "2100", False, ""),
    ("Aparatología", "Mantenedor de espacio con banda", "1250", "1100", False, ""),
    ("Aparatología", "Mantenedor de espacio con corona", "2050", "1800", False, ""),
    ("Aparatología", "Hirax", "2600", "2200", False, ""),
]


def crear_catalogo(apps, schema_editor):
    Convenio = apps.get_model("catalog", "Convenio")
    CategoriaServicio = apps.get_model("catalog", "CategoriaServicio")
    Servicio = apps.get_model("catalog", "Servicio")
    PrecioConvenio = apps.get_model("catalog", "PrecioConvenio")

    convenios = [Convenio.objects.get_or_create(nombre=nombre)[0] for nombre in CONVENIOS]

    categorias = {}
    for nombre, orden in CATEGORIAS:
        categorias[nombre], _ = CategoriaServicio.objects.get_or_create(
            nombre=nombre, defaults={"orden": orden}
        )

    for orden, (cat_nombre, nombre, precio_general, precio_convenio, destacado, descripcion) in enumerate(
        SERVICIOS, start=1
    ):
        servicio = Servicio.objects.create(
            categoria=categorias[cat_nombre],
            nombre=nombre,
            descripcion_breve=descripcion,
            precio_general=Decimal(precio_general),
            destacado=destacado,
            orden=orden,
        )
        if precio_convenio is not None:
            for convenio in convenios:
                PrecioConvenio.objects.create(
                    servicio=servicio,
                    convenio=convenio,
                    precio_especial=Decimal(precio_convenio),
                )


def eliminar_catalogo(apps, schema_editor):
    Servicio = apps.get_model("catalog", "Servicio")
    CategoriaServicio = apps.get_model("catalog", "CategoriaServicio")
    Convenio = apps.get_model("catalog", "Convenio")
    Servicio.objects.all().delete()
    CategoriaServicio.objects.filter(nombre__in=[c for c, _ in CATEGORIAS]).delete()
    Convenio.objects.filter(nombre__in=CONVENIOS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_catalogo, eliminar_catalogo),
    ]
