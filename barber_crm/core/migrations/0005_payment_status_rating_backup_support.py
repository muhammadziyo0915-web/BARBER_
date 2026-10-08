# Generated manually for BARBER AURA v2 additions.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_alter_barber_user_alter_customer_notify_minutes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="rating_sent",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Kutilmoqda"),
                    ("paid", "To‘langan"),
                    ("failed", "Muvaffaqiyatsiz"),
                    ("refunded", "Qaytarilgan"),
                ],
                default="paid",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="transaction_id",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="payment",
            name="provider_reference",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
