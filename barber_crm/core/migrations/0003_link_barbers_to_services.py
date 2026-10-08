from django.db import migrations


def link_all(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    Barber = apps.get_model("core", "Barber")
    barbers = list(Barber.objects.all())
    for service in Service.objects.all():
        if service.barbers.exists():
            service.barbers.add(*barbers)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_crm_upgrade")]
    operations = [migrations.RunPython(link_all, migrations.RunPython.noop)]
