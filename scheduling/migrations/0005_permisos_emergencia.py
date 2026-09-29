from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


def actualizar_permisos(apps, schema_editor):
    # Igual que en core/migrations/0003_grupos_permisos.py: si todo el
    # proyecto se migra desde cero en una sola llamada, los permisos de
    # SolicitudEmergencia (creada en la migración anterior) todavía no
    # existirían aquí sin forzar su creación explícitamente.
    create_permissions(global_apps.get_app_config("scheduling"), apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="scheduling", model="solicitudemergencia")

    doctor, _ = Group.objects.get_or_create(name="Doctor")
    doctor.permissions.add(*Permission.objects.filter(content_type=ct))

    secretaria, _ = Group.objects.get_or_create(name="Secretaria")
    perms = Permission.objects.filter(
        content_type=ct,
        codename__in=["add_solicitudemergencia", "change_solicitudemergencia", "view_solicitudemergencia"],
    )
    secretaria.permissions.add(*perms)


def revertir_permisos(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    ct = ContentType.objects.filter(app_label="scheduling", model="solicitudemergencia").first()
    if ct:
        perms = Permission.objects.filter(content_type=ct)
        for group in apps.get_model("auth", "Group").objects.filter(name__in=["Doctor", "Secretaria"]):
            group.permissions.remove(*perms)


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0004_solicitudemergencia"),
        # Necesitamos que los grupos Doctor/Secretaria ya existan (los crea
        # esta migración de core); sin esta dependencia explícita, el orden
        # entre apps distintas no está garantizado.
        ("core", "0003_grupos_permisos"),
    ]

    operations = [
        migrations.RunPython(actualizar_permisos, revertir_permisos),
    ]
