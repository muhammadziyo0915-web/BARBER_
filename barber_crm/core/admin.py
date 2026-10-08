from django.contrib import admin
from .models import Profile, Barber, BarberTimeOff, Customer, Service, ServiceImage, Appointment, Payment, BarberSettlement, Expense, Notification, Rating

admin.site.register([Profile, Barber, BarberTimeOff, Customer, Service, ServiceImage, Appointment, Payment, BarberSettlement, Expense, Notification, Rating])
