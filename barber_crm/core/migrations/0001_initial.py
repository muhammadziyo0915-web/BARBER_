from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.CreateModel(
            name="Barber",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("specialization", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("experience", models.PositiveIntegerField(default=0)),
                ("salary_percent", models.DecimalField(decimal_places=2, default=50, max_digits=5)),
                ("is_active", models.BooleanField(default=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=80)),
                ("last_name", models.CharField(blank=True, max_length=80)),
                ("phone", models.CharField(max_length=30)),
                ("telegram_chat_id", models.CharField(blank=True, max_length=80)),
                ("notify_minutes", models.PositiveIntegerField(default=30)),
                ("birthday", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("duration", models.PositiveIntegerField(default=30, help_text="Daqiqa")),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Appointment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("waiting", "Kutilmoqda"), ("confirmed", "Tasdiqlangan"), ("progress", "Jarayonda"), ("done", "Tugallangan"), ("cancelled", "Bekor qilingan")], default="waiting", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("reminder_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("barber", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.barber")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.customer")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.service")),
            ],
            options={"ordering": ["date", "start_time"]},
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("payment_method", models.CharField(choices=[("cash", "Naqd"), ("card", "Karta"), ("click", "Click"), ("payme", "Payme")], default="cash", max_length=20)),
                ("paid_at", models.DateTimeField(auto_now_add=True)),
                ("appointment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.appointment")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.customer")),
            ],
        ),
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("category", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
