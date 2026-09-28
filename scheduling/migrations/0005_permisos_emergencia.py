from django.db import migrations


def actualizar_permisos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="scheduling", model="solicitudemergencia")

    doctor = Group.objects.filter(name="Doctor").first()
    if doctor:
        doctor.permissions.add(*Permission.objects.filter(content_type=ct))

    secretaria = Group.objects.filter(name="Secretaria").first()
    if secretaria:
        perms = Permission.objects.filter(
            content_type=ct, codename__in=["add_solicitudemergencia", "change_solicitudemergencia", "view_solicitudemergencia"]
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
    ]

    operations = [
        migrations.RunPython(actualizar_permisos, revertir_permisos),
    ]
