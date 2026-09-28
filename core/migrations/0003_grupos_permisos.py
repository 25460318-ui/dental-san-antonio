from django.db import migrations

DOCTOR_FULL = [
    ("scheduling", "cita"),
    ("scheduling", "bloqueoagenda"),
    ("scheduling", "aviso"),
    ("scheduling", "horarioatencion"),
    ("scheduling", "paciente"),
    ("catalog", "categoriaservicio"),
    ("catalog", "servicio"),
    ("catalog", "convenio"),
    ("catalog", "precioconvenio"),
    ("core", "clinicinfo"),
]

# (app_label, model, [acciones])
SECRETARIA_PERMS = [
    ("scheduling", "cita", ["add", "change", "view"]),
    ("scheduling", "bloqueoagenda", ["add", "change", "view"]),
    ("scheduling", "aviso", ["view"]),
    ("scheduling", "horarioatencion", ["view"]),
    ("scheduling", "paciente", ["add", "change", "view"]),
    ("catalog", "categoriaservicio", ["add", "change", "view"]),
    ("catalog", "servicio", ["add", "change", "view"]),
    ("catalog", "convenio", ["add", "change", "view"]),
    ("catalog", "precioconvenio", ["add", "change", "view"]),
    ("core", "clinicinfo", ["view"]),
]


def crear_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    def get_ct(app_label, model):
        return ContentType.objects.get(app_label=app_label, model=model)

    doctor, _ = Group.objects.get_or_create(name="Doctor")
    doctor_perms = Permission.objects.filter(
        content_type__in=[get_ct(a, m) for a, m in DOCTOR_FULL]
    )
    doctor.permissions.set(doctor_perms)

    secretaria, _ = Group.objects.get_or_create(name="Secretaria")
    secretaria_perms = []
    for app_label, model, acciones in SECRETARIA_PERMS:
        ct = get_ct(app_label, model)
        for accion in acciones:
            secretaria_perms.append(
                Permission.objects.get(content_type=ct, codename=f"{accion}_{model}")
            )
    secretaria.permissions.set(secretaria_perms)


def eliminar_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["Doctor", "Secretaria"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_clinicinfo_dolor_recargo_monto_and_more"),
        ("catalog", "0001_initial"),
        ("scheduling", "0002_cita_recargo_dolor"),
    ]

    operations = [
        migrations.RunPython(crear_grupos, eliminar_grupos),
    ]
