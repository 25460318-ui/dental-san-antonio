from django.db import migrations

DESCRIPCIONES = {
    "Servicios generales": "Consultas, limpiezas y extracciones.",
    "Restauraciones y estética": "Resinas, coronas y blanqueamiento.",
    "Prótesis": "Puentes y placas removibles.",
    "Especialidades": "Endodoncia, cirugía e implantes.",
    "Urgencias": "Atención inmediata para emergencias.",
    "Odontopediatría": "Cuidado dental para niños.",
    "Aparatología": "Ortodoncia y aparatos correctivos.",
}


def actualizar_descripciones(apps, schema_editor):
    CategoriaServicio = apps.get_model("catalog", "CategoriaServicio")
    for nombre, descripcion in DESCRIPCIONES.items():
        CategoriaServicio.objects.filter(nombre=nombre, descripcion_corta="").update(
            descripcion_corta=descripcion
        )


def revertir_descripciones(apps, schema_editor):
    CategoriaServicio = apps.get_model("catalog", "CategoriaServicio")
    CategoriaServicio.objects.filter(nombre__in=DESCRIPCIONES.keys()).update(descripcion_corta="")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_seed_catalogo"),
    ]

    operations = [
        migrations.RunPython(actualizar_descripciones, revertir_descripciones),
    ]
