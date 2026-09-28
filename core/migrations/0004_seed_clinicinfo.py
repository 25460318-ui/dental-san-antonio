from django.db import migrations


def crear_clinic_info(apps, schema_editor):
    ClinicInfo = apps.get_model("core", "ClinicInfo")
    if not ClinicInfo.objects.exists():
        ClinicInfo.objects.create(
            pk=1,
            nombre="Dental San Antonio",
            direccion="Tekuan 100, Villa Izcalli, Villa de Álvarez, Colima.",
            telefono_1="312 396 6831",
            telefono_2="312 109 5794",
            email="sanantoniodental4@gmail.com",
            # facebook_url / instagram_url se dejan vacíos: solo tenemos el nombre de
            # página ("Dental San Antonio") y el usuario ("@DENTALSANANTONIOCOLIMA"),
            # no el enlace real. Se completan desde el admin cuando se tenga el link exacto.
            mensaje_hero="Cuidamos tu sonrisa con calidez y profesionalismo. (mensaje temporal)",
        )


def eliminar_clinic_info(apps, schema_editor):
    ClinicInfo = apps.get_model("core", "ClinicInfo")
    ClinicInfo.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_grupos_permisos"),
    ]

    operations = [
        migrations.RunPython(crear_clinic_info, eliminar_clinic_info),
    ]
