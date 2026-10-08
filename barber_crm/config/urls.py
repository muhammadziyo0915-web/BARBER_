from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls), path("", views.dashboard, name="dashboard"), path("login/", views.login_view, name="login"), path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"), path("book/", views.public_booking, name="public_booking"), path("appointments/", views.appointments, name="appointments"), path("appointments/<int:pk>/status/", views.appointment_status, name="appointment_status"),
    path("barber/appointments/", views.barber_appointments, name="barber_appointments"), path("customers/", views.customers, name="customers"), path("barbers/", views.barbers, name="barbers"), path("barbers/<int:pk>/delete/", views.barber_delete, name="barber_delete"), path("barbers/<int:pk>/toggle/", views.barber_toggle, name="barber_toggle"),
    path("services/", views.services, name="services"), path("services/<int:pk>/edit/", views.service_edit, name="service_edit"), path("services/<int:pk>/toggle/", views.service_toggle, name="service_toggle"), path("services/image/<int:pk>/delete/", views.service_image_delete, name="service_image_delete"), path("services/<int:pk>/delete/", views.service_delete, name="service_delete"),
    path("payments/", views.payments, name="payments"), path("settlements/", views.settlements, name="settlements"), path("expenses/", views.expenses, name="expenses"), path("reports/", views.reports, name="reports"), path("assistant/", views.assistant, name="assistant"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
