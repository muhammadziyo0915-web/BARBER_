import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.contrib.auth.models import User
from core.models import Barber, Service, Profile

user, created = User.objects.get_or_create(username='director')
if created:
    user.set_password('admin12345'); user.first_name='Barber'; user.last_name='Director'; user.is_staff=True; user.is_superuser=True; user.save()
Profile.objects.update_or_create(user=user, defaults={'role':'director'})
barber_user, _ = User.objects.get_or_create(username='barber1', defaults={'first_name':'Ali','last_name':'Barber'})
if not barber_user.has_usable_password(): barber_user.set_password('barber12345'); barber_user.save()
barber,_=Barber.objects.get_or_create(user=barber_user, defaults={'specialization':'Premium Barber','phone':'+998901234567','experience':5,'work_start':'09:00','work_end':'20:00'})
Profile.objects.update_or_create(user=barber_user, defaults={'role':'barber','phone':barber.phone})
for name, price, duration in [('Classic Haircut',30000,60),('Fade',40000,60),('Beard Trim',20000,30),('Haircut + Beard',50000,90),('Premium Styling',60000,120)]:
    service,_=Service.objects.get_or_create(name=name, defaults={'price':price,'duration':duration,'description':'Professional barber service'})
    service.barbers.add(barber)
print('Demo tayyor: director / admin12345 | barber1 / barber12345')
