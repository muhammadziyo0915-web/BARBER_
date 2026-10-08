from django.contrib.auth.models import User
from django.db import models

class Profile(models.Model):
    ROLE_CHOICES = [("director", "Direktor"), ("barber", "Sartarosh")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="director")
    photo = models.FileField(upload_to="profiles/", blank=True, null=True)
    telegram_chat_id = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

class Barber(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="barber")
    specialization = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    experience = models.PositiveIntegerField(default=0)
    salary_percent = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    is_active = models.BooleanField(default=True)
    photo = models.FileField(upload_to="barbers/", blank=True, null=True)
    work_start = models.TimeField(default="09:00")
    work_end = models.TimeField(default="20:00")
    working_days = models.CharField(max_length=30, default="0,1,2,3,4,5")

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def works_on(self, d):
        return str(d.weekday()) in {x.strip() for x in self.working_days.split(",") if x.strip()}

class BarberTimeOff(models.Model):
    barber = models.ForeignKey(Barber, on_delete=models.CASCADE, related_name="time_offs")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]

class Customer(models.Model):
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30)
    telegram_chat_id = models.CharField(max_length=80, blank=True)
    notify_minutes = models.PositiveIntegerField(default=60)
    birthday = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

class Service(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=0)
    duration = models.PositiveIntegerField(default=60, help_text="Daqiqa")
    barbers = models.ManyToManyField(Barber, blank=True, related_name="services")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ServiceImage(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(upload_to="services/")
    caption = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

class Appointment(models.Model):
    STATUS_CHOICES = [
        ("waiting", "Kutilmoqda"), ("confirmed", "Tasdiqlangan"),
        ("progress", "Jarayonda"), ("done", "Tugallangan"), ("cancelled", "Bekor qilingan"),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    barber = models.ForeignKey(Barber, on_delete=models.PROTECT)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    notes = models.TextField(blank=True)
    price_snapshot = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    duration_snapshot = models.PositiveIntegerField(default=60)
    reminder_sent = models.BooleanField(default=False)
    rating_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]

    def save(self, *args, **kwargs):
        if not self.price_snapshot and self.service_id:
            self.price_snapshot = self.service.price
        if not self.duration_snapshot and self.service_id:
            self.duration_snapshot = self.service.duration
        if self.start_time and self.duration_snapshot:
            from datetime import datetime, timedelta
            end = datetime.combine(self.date, self.start_time) + timedelta(minutes=self.duration_snapshot)
            self.end_time = end.time()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer} — {self.service}"

class Payment(models.Model):
    METHOD_CHOICES = [("cash", "Naqd"), ("card", "Karta"), ("click", "Click"), ("payme", "Payme")]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    STATUS_CHOICES = [("pending", "Kutilmoqda"), ("paid", "To‘langan"), ("failed", "Muvaffaqiyatsiz"), ("refunded", "Qaytarilgan")]
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="cash")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="paid")
    transaction_id = models.CharField(max_length=160, blank=True)
    provider_reference = models.CharField(max_length=160, blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)

class BarberSettlement(models.Model):
    barber = models.ForeignKey(Barber, on_delete=models.PROTECT, related_name="settlements")
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField()
    paid_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

class Expense(models.Model):
    title = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notifications")
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Rating(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="rating")
    stars = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
