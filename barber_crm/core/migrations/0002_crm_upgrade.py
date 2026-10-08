from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    def backfill(apps, schema_editor):
        User = apps.get_model("auth", "User")
        Profile = apps.get_model("core", "Profile")
        Barber = apps.get_model("core", "Barber")
        Appointment = apps.get_model("core", "Appointment")
        Service = apps.get_model("core", "Service")
        for u in User.objects.filter(is_staff=True):
            Profile.objects.get_or_create(user=u, defaults={"role": "director"})
        for b in Barber.objects.all():
            Profile.objects.get_or_create(user=b.user, defaults={"role": "barber", "phone": b.phone})
        for s in Service.objects.all():
            if s.price < 1000:
                s.price = s.price * 1000
                s.save(update_fields=["price"])
        for model in [apps.get_model("core", "Payment"), apps.get_model("core", "Expense")]:
            for row in model.objects.all():
                if row.amount < 1000:
                    row.amount = row.amount * 1000
                    row.save(update_fields=["amount"])
        for a in Appointment.objects.select_related("service"):
            if not a.price_snapshot: a.price_snapshot = a.service.price
            if not a.duration_snapshot: a.duration_snapshot = a.service.duration
            a.save(update_fields=["price_snapshot", "duration_snapshot"])

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("director", "Direktor"), ("barber", "Sartarosh")], default="director", max_length=20)),
                ("photo", models.FileField(blank=True, null=True, upload_to="profiles/")),
                ("telegram_chat_id", models.CharField(blank=True, max_length=80)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to="auth.user")),
            ],
        ),
        migrations.AddField(model_name="barber", name="photo", field=models.FileField(blank=True, null=True, upload_to="barbers/")),
        migrations.AddField(model_name="barber", name="work_start", field=models.TimeField(default="09:00")),
        migrations.AddField(model_name="barber", name="work_end", field=models.TimeField(default="20:00")),
        migrations.AddField(model_name="barber", name="working_days", field=models.CharField(default="0,1,2,3,4,5", max_length=30)),
        migrations.CreateModel(
            name="BarberTimeOff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()), ("start_time", models.TimeField()), ("end_time", models.TimeField()),
                ("reason", models.CharField(blank=True, max_length=255)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("barber", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="time_offs", to="core.barber")),
            ], options={"ordering": ["date", "start_time"]},
        ),
        migrations.AddField(model_name="service", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AddField(model_name="service", name="barbers", field=models.ManyToManyField(blank=True, related_name="services", to="core.barber")),
        migrations.AlterField(model_name="service", name="price", field=models.DecimalField(decimal_places=0, max_digits=12)),
        migrations.CreateModel(
            name="ServiceImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.FileField(upload_to="services/")), ("caption", models.CharField(blank=True, max_length=160)), ("sort_order", models.PositiveIntegerField(default=0)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="core.service")),
            ], options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddField(model_name="appointment", name="price_snapshot", field=models.DecimalField(decimal_places=0, default=0, max_digits=12)),
        migrations.AddField(model_name="appointment", name="duration_snapshot", field=models.PositiveIntegerField(default=60)),
        migrations.AlterField(model_name="appointment", name="reminder_sent", field=models.BooleanField(default=False)),
        migrations.AlterField(model_name="payment", name="amount", field=models.DecimalField(decimal_places=0, max_digits=12)),
        migrations.AlterField(model_name="expense", name="amount", field=models.DecimalField(decimal_places=0, max_digits=12)),
        migrations.CreateModel(
            name="BarberSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=12)), ("period_start", models.DateField(blank=True, null=True)), ("period_end", models.DateField()), ("paid_at", models.DateTimeField(auto_now_add=True)), ("note", models.CharField(blank=True, max_length=255)),
                ("barber", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settlements", to="core.barber")),
            ],
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField()), ("sent", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("appointment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="core.appointment")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="core.profile")),
            ],
        ),
        migrations.CreateModel(
            name="Rating",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("stars", models.PositiveSmallIntegerField()), ("comment", models.TextField(blank=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("appointment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="rating", to="core.appointment")),
            ],
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
