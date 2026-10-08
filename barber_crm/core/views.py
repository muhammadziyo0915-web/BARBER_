from datetime import datetime, timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Barber, BarberTimeOff, BarberSettlement, Customer, Service, ServiceImage, Appointment, Payment, Expense, Profile, Rating, Notification


def ensure_profile(user, role=None):
    profile, _ = Profile.objects.get_or_create(user=user, defaults={"role": role or ("director" if user.is_staff else "barber")})
    if role and profile.role != role:
        profile.role = role; profile.save(update_fields=["role"])
    return profile


def is_director(user):
    return user.is_superuser or user.is_staff or getattr(getattr(user, "profile", None), "role", "") == "director"


def barber_for(user):
    return Barber.objects.filter(user=user, is_active=True).select_related("user").first()


def director_required(view):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect("login")
        if not is_director(request.user):
            messages.error(request, "Bu bo‘lim faqat direktor uchun.")
            return redirect("dashboard")
        ensure_profile(request.user, "director")
        return view(request, *args, **kwargs)
    return wrapped


def login_view(request):
    if request.user.is_authenticated: return redirect("dashboard")
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user); ensure_profile(user); return redirect("dashboard")
        messages.error(request, "Login yoki parol noto‘g‘ri.")
    return render(request, "core/login.html")


def logout_view(request):
    logout(request); return redirect("login")


def _money(qs): return qs.aggregate(x=Sum("amount"))["x"] or Decimal("0")


def _salary_due(barber):
    last = barber.settlements.order_by("-paid_at").first()
    qs = Appointment.objects.filter(barber=barber, status="done")
    if last and last.period_end:
        qs = qs.filter(date__gt=last.period_end)
    gross = sum((x.price_snapshot for x in qs), Decimal("0"))
    return (gross * barber.salary_percent / Decimal("100")).quantize(Decimal("1"))


def _notify_profiles(message, appointment=None, barber=None):
    profiles = list(Profile.objects.filter(role="director"))
    if barber:
        profiles += list(Profile.objects.filter(user=barber.user))
    for p in {x.pk: x for x in profiles}.values():
        if p.telegram_chat_id:
            Notification.objects.create(recipient=p, appointment=appointment, message=message)


@login_required
def dashboard(request):
    today = timezone.localdate()
    barber = barber_for(request.user) if not is_director(request.user) else None
    if barber:
        apps = Appointment.objects.filter(barber=barber, date=today).select_related("customer", "barber", "service")
        upcoming = Appointment.objects.filter(barber=barber, date__gte=today).exclude(status="cancelled").select_related("customer", "service")[:8]
        income = _money(Payment.objects.filter(appointment__barber=barber, paid_at__date=today))
        context = {"today":today,"today_apps":apps.count(),"today_done":apps.filter(status="done").count(),"today_income":income,"month_income":_money(Payment.objects.filter(appointment__barber=barber, paid_at__year=today.year, paid_at__month=today.month)),"month_expense":Decimal("0"),"customers_count":Customer.objects.filter(appointment__barber=barber).distinct().count(),"barbers_count":1,"services_count":barber.services.filter(is_active=True).count(),"appointments":apps[:10],"upcoming":upcoming,"role":"barber","barber":barber,"salary_due":_salary_due(barber)}
    else:
        apps = Appointment.objects.filter(date=today).select_related("customer","barber","service")
        context = {"today":today,"today_apps":apps.count(),"today_done":apps.filter(status="done").count(),"today_income":_money(Payment.objects.filter(paid_at__date=today)),"month_income":_money(Payment.objects.filter(paid_at__year=today.year, paid_at__month=today.month)),"month_expense":_money(Expense.objects.filter(date__year=today.year,date__month=today.month)),"customers_count":Customer.objects.count(),"barbers_count":Barber.objects.filter(is_active=True).count(),"services_count":Service.objects.filter(is_active=True).count(),"appointments":apps[:10],"upcoming":Appointment.objects.filter(date__gte=today).exclude(status="cancelled").select_related("customer","barber","service")[:8],"role":"director"}
    return render(request,"core/dashboard.html",context)


@director_required
def customers(request):
    if request.method == "POST":
        Customer.objects.create(first_name=request.POST.get("first_name",""),last_name=request.POST.get("last_name",""),phone=request.POST.get("phone",""),telegram_chat_id=request.POST.get("telegram_chat_id",""),notify_minutes=request.POST.get("notify_minutes") or 60,birthday=request.POST.get("birthday") or None,notes=request.POST.get("notes",""))
        messages.success(request,"Mijoz qo‘shildi."); return redirect("customers")
    q=request.GET.get("q","").strip(); items=Customer.objects.all().order_by("-created_at")
    if q: items=items.filter(Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(phone__icontains=q))
    return render(request,"core/customers.html",{"items":items,"q":q})


@director_required
def barbers(request):
    if request.method == "POST":
        username=request.POST.get("username","").strip(); password=request.POST.get("password","")
        if not username or not password: messages.error(request,"Username va parol kerak."); return redirect("barbers")
        if User.objects.filter(username=username).exists(): messages.error(request,"Bu username band."); return redirect("barbers")
        user=User.objects.create_user(username=username,password=password,first_name=request.POST.get("first_name",""),last_name=request.POST.get("last_name",""))
        barber=Barber.objects.create(user=user,specialization=request.POST.get("specialization",""),phone=request.POST.get("phone",""),experience=request.POST.get("experience") or 0,salary_percent=request.POST.get("salary_percent") or 50,work_start=request.POST.get("work_start") or "09:00",work_end=request.POST.get("work_end") or "20:00",working_days=request.POST.get("working_days") or "0,1,2,3,4,5")
        ensure_profile(user,"barber"); barber.services.set(Service.objects.all()); messages.success(request,f"{barber} qo‘shildi."); return redirect("barbers")
    return render(request,"core/barbers.html",{"items":Barber.objects.select_related("user").all()})


@director_required
def barber_delete(request, pk):
    barber=get_object_or_404(Barber,pk=pk)
    if request.method=="POST":
        if barber.user.is_superuser or barber.user.is_staff:
            messages.error(request,"Direktor akkauntini bu yerdan o‘chirib bo‘lmaydi.")
        elif Appointment.objects.filter(barber=barber).exists() or BarberSettlement.objects.filter(barber=barber).exists():
            messages.warning(request,f"{barber} bo‘yicha navbat yoki hisob-kitob yozuvlari bor, shuning uchun o‘chirib bo‘lmaydi. Uni «Yashirish» tugmasi bilan nofaol qiling.")
        else:
            name=str(barber)
            if barber.photo:
                try: barber.photo.delete(save=False)
                except Exception: pass
            barber.user.delete()
            messages.success(request,f"{name} o‘chirildi.")
    return redirect("barbers")


@director_required
def barber_toggle(request, pk):
    barber=get_object_or_404(Barber,pk=pk)
    if request.method=="POST":
        barber.is_active=not barber.is_active; barber.save(update_fields=["is_active"])
        messages.success(request,f"{barber} {'faollashtirildi' if barber.is_active else 'yashirildi'}.")
    return redirect("barbers")


@director_required
def services(request):
    if request.method=="POST":
        with transaction.atomic():
            price=request.POST.get("custom_price") or request.POST.get("price") or 0
            service=Service.objects.create(name=request.POST.get("name",""),price=price,duration=request.POST.get("duration") or 60,description=request.POST.get("description",""))
            ids=request.POST.getlist("barbers"); service.barbers.set(ids)
            files=request.FILES.getlist("images")
            for i,f in enumerate(files): ServiceImage.objects.create(service=service,image=f,sort_order=i)
        if len(request.FILES.getlist("images")) < 3: messages.warning(request,"Xizmat saqlandi, lekin tavsiya etilgan kamida 3 ta namuna rasmi yuklanmadi.")
        else: messages.success(request,"Xizmat qo‘shildi.")
        return redirect("services")
    return render(request,"core/services.html",{"items":Service.objects.prefetch_related("images","barbers__user").order_by("name"),"barbers":Barber.objects.filter(is_active=True)})


@director_required
def service_edit(request, pk):
    service=get_object_or_404(Service,pk=pk)
    if request.method=="POST":
        service.name=request.POST.get("name",service.name); service.price=request.POST.get("price") or service.price; service.duration=request.POST.get("duration") or service.duration; service.description=request.POST.get("description",""); service.is_active=request.POST.get("is_active") == "on"; service.save(); service.barbers.set(request.POST.getlist("barbers"))
        files=request.FILES.getlist("images")
        start=service.images.count()
        for i,f in enumerate(files,start): ServiceImage.objects.create(service=service,image=f,sort_order=i)
        messages.success(request,"Xizmat yangilandi."); return redirect("services")
    return render(request,"core/service_edit.html",{"service":service,"barbers":Barber.objects.filter(is_active=True)})


@director_required
def service_delete(request, pk):
    service=get_object_or_404(Service,pk=pk)
    if request.method=="POST":
        if Appointment.objects.filter(service=service).exists():
            messages.warning(request,"Bu xizmat bo‘yicha navbatlar mavjud, shuning uchun o‘chirib bo‘lmaydi. Uni «Yashirish» tugmasi bilan nofaol qiling.")
        else:
            name=service.name
            for img in service.images.all():
                try: img.image.delete(save=False)
                except Exception: pass
            service.delete(); messages.success(request,f"«{name}» xizmati o‘chirildi.")
    return redirect("services")


@director_required
def service_image_delete(request, pk):
    img=get_object_or_404(ServiceImage,pk=pk); service_id=img.service_id
    if request.method=="POST":
        try: img.image.delete(save=False)
        except Exception: pass
        img.delete(); messages.success(request,"Rasm o‘chirildi.")
    return redirect("service_edit",pk=service_id)


@director_required
def service_toggle(request, pk):
    service=get_object_or_404(Service,pk=pk); service.is_active=not service.is_active; service.save(update_fields=["is_active"]); messages.success(request,"Xizmat holati o‘zgartirildi."); return redirect("services")


def _appointment_from_data(data, customer, actor_barber=None):
    service=get_object_or_404(Service,id=data["service"],is_active=True)
    date=datetime.strptime(data["date"],"%Y-%m-%d").date(); start=datetime.strptime(data["start_time"],"%H:%M").time()
    barber=get_object_or_404(Barber,id=data["barber"],is_active=True)
    if actor_barber and barber.pk != actor_barber.pk: raise ValueError("Faqat o‘zingizga navbat yaratishingiz mumkin.")
    if service.barbers.exists() and not service.barbers.filter(pk=barber.pk).exists(): raise ValueError("Bu xizmatni tanlangan barber bajarmaydi.")
    if not barber.works_on(date): raise ValueError("Bu kuni sartarosh ishlamaydi.")
    end=(datetime.combine(date,start)+timedelta(minutes=service.duration)).time()
    if start < barber.work_start or end > barber.work_end: raise ValueError("Bu vaqt sartaroshning ish vaqtiga kirmaydi.")
    off=BarberTimeOff.objects.filter(barber=barber,date=date,start_time__lt=end,end_time__gt=start).exists()
    if off: raise ValueError("Bu vaqt sartarosh tomonidan vaqtincha yopilgan.")
    clash=Appointment.objects.filter(barber=barber,date=date,status__in=["waiting","confirmed","progress"],start_time__lt=end,end_time__gt=start).exists()
    if clash: raise ValueError("Bu sartaroshning shu vaqtda boshqa navbati bor.")
    return Appointment.objects.create(customer=customer,barber=barber,service=service,date=date,start_time=start,end_time=end,status=data.get("status","waiting"),notes=data.get("notes",""),price_snapshot=service.price,duration_snapshot=service.duration)


@director_required
def appointments(request):
    if request.method=="POST":
        try:
            customer=get_object_or_404(Customer,id=request.POST["customer"]); ap=_appointment_from_data(request.POST,customer); _notify_profiles(f"🔔 Yangi navbat!\n👤 {customer}\n💈 {ap.barber}\n✂ {ap.service.name}\n📅 {ap.date:%d.%m.%Y}\n🕐 {ap.start_time:%H:%M}–{ap.end_time:%H:%M}\n💰 {ap.price_snapshot:,.0f} so‘m",ap,ap.barber); messages.success(request,"Navbat yaratildi.")
        except Exception as e: messages.error(request,str(e))
        return redirect("appointments")
    date_filter=request.GET.get("date",""); items=Appointment.objects.select_related("customer","barber","service").all()
    if date_filter: items=items.filter(date=date_filter)
    return render(request,"core/appointments.html",{"items":items,"customers":Customer.objects.all(),"barbers":Barber.objects.filter(is_active=True),"services":Service.objects.filter(is_active=True),"date_filter":date_filter,"today":timezone.localdate()})


@login_required
def barber_appointments(request):
    barber=barber_for(request.user)
    if not barber: return redirect("dashboard")
    if request.method=="POST" and request.POST.get("action")=="timeoff":
        BarberTimeOff.objects.create(barber=barber,date=request.POST["date"],start_time=request.POST["start_time"],end_time=request.POST["end_time"],reason=request.POST.get("reason","")); messages.success(request,"Vaqt yopildi."); return redirect("barber_appointments")
    if request.method=="POST" and request.POST.get("action")=="status":
        ap=get_object_or_404(Appointment,pk=request.POST["pk"],barber=barber); ap.status=request.POST["status"]; ap.save(update_fields=["status"]); messages.success(request,"Navbat holati yangilandi."); return redirect("barber_appointments")
    items=Appointment.objects.filter(barber=barber,date__gte=timezone.localdate()).exclude(status="cancelled").select_related("customer","service")
    return render(request,"core/barber_appointments.html",{"barber":barber,"items":items,"timeoffs":barber.time_offs.filter(date__gte=timezone.localdate())[:20]})


@login_required
def profile_view(request):
    profile=ensure_profile(request.user); barber=Barber.objects.filter(user=request.user).first()
    if request.method=="POST":
        request.user.first_name=request.POST.get("first_name",request.user.first_name); request.user.last_name=request.POST.get("last_name",request.user.last_name); request.user.save(update_fields=["first_name","last_name"])
        profile.phone=request.POST.get("phone",profile.phone); profile.telegram_chat_id=request.POST.get("telegram_chat_id",profile.telegram_chat_id)
        if request.FILES.get("photo"): profile.photo=request.FILES["photo"]
        profile.save()
        if barber:
            barber.phone=profile.phone or request.POST.get("barber_phone",barber.phone); barber.specialization=request.POST.get("specialization",barber.specialization)
            if request.FILES.get("barber_photo"): barber.photo=request.FILES["barber_photo"]
            barber.save()
        messages.success(request,"Profil saqlandi."); return redirect("profile")
    return render(request,"core/profile.html",{"profile":profile,"barber":barber})


def public_booking(request):
    if request.method=="POST":
        try:
            customer,_=Customer.objects.get_or_create(phone=request.POST["phone"],defaults={"first_name":request.POST["first_name"],"last_name":request.POST.get("last_name","")})
            customer.first_name=request.POST["first_name"]; customer.last_name=request.POST.get("last_name",""); customer.telegram_chat_id=request.POST.get("telegram_chat_id",""); customer.save()
            ap=_appointment_from_data(request.POST,customer); _notify_profiles(f"🔔 Yangi online navbat!\n👤 {customer}\n💈 {ap.barber}\n✂ {ap.service.name}\n📅 {ap.date:%d.%m.%Y}\n🕐 {ap.start_time:%H:%M}–{ap.end_time:%H:%M}\n💰 {ap.price_snapshot:,.0f} so‘m",ap,ap.barber); messages.success(request,"Navbatingiz qabul qilindi!")
        except Exception as e: messages.error(request,str(e))
    return render(request,"core/booking.html",{"services":Service.objects.filter(is_active=True),"barbers":Barber.objects.filter(is_active=True),"today":timezone.localdate(),"role":"director" if request.user.is_authenticated and is_director(request.user) else ("barber" if request.user.is_authenticated else "")})


@director_required
def appointment_status(request,pk):
    ap=get_object_or_404(Appointment,pk=pk); old=ap.status; ap.status=request.POST.get("status",ap.status); ap.save(update_fields=["status"])
    if old != ap.status and ap.barber.user.profile.telegram_chat_id:
        Notification.objects.create(recipient=ap.barber.user.profile,appointment=ap,message=f"🔔 Navbat #{ap.id} holati: {ap.get_status_display()}")
    if ap.status=="done" and ap.customer.telegram_chat_id:
        # Rating link is represented by bot message; no external URL required.
        pass
    messages.success(request,"Navbat holati yangilandi."); return redirect("appointments")


@director_required
def payments(request):
    if request.method=="POST":
        amount=request.POST.get("amount")
        method=request.POST.get("payment_method","cash")
        status=request.POST.get("status","paid")
        Payment.objects.create(
            customer_id=request.POST["customer"],
            appointment_id=request.POST.get("appointment") or None,
            amount=amount,
            payment_method=method,
            status=status,
            transaction_id=request.POST.get("transaction_id","").strip(),
            provider_reference=request.POST.get("provider_reference","").strip(),
        )
        messages.success(request, "To‘lov saqlandi.")
        return redirect("payments")
    items=Payment.objects.select_related("customer","appointment").order_by("-paid_at")[:150]
    paid_qs=Payment.objects.filter(status="paid")
    totals={key:_money(paid_qs.filter(payment_method=key)) for key,_ in Payment.METHOD_CHOICES}
    return render(request,"core/payments.html",{
        "items":items,"total":_money(paid_qs),"totals":totals,
        "customers":Customer.objects.all(),
        "appointments":Appointment.objects.exclude(status="cancelled").order_by("-date","-start_time")[:150],
    })


@director_required
def settlements(request):
    if request.method=="POST":
        barber=get_object_or_404(Barber,pk=request.POST["barber"]); amount=_salary_due(barber); end=timezone.localdate(); last=barber.settlements.order_by("-paid_at").first(); start=(last.period_end+timedelta(days=1)) if last else None; BarberSettlement.objects.create(barber=barber,amount=amount,period_start=start,period_end=end,note=request.POST.get("note","")); messages.success(request,f"{barber} uchun {amount:,.0f} so‘mlik hisob-kitob yopildi."); return redirect("settlements")
    rows=[{"barber":b,"due":_salary_due(b)} for b in Barber.objects.filter(is_active=True).select_related("user")]
    return render(request,"core/settlements.html",{"rows":rows,"history":BarberSettlement.objects.select_related("barber","barber__user").order_by("-paid_at")[:50]})


@director_required
def expenses(request):
    if request.method=="POST": Expense.objects.create(title=request.POST["title"],amount=request.POST["amount"],category=request.POST.get("category",""),description=request.POST.get("description",""),date=request.POST["date"]); messages.success(request,"Xarajat saqlandi."); return redirect("expenses")
    return render(request,"core/expenses.html",{"items":Expense.objects.all().order_by("-date")[:100]})


@director_required
def reports(request):
    selected=request.GET.get("date","").strip()
    try:
        report_date=datetime.strptime(selected,"%Y-%m-%d").date() if selected else timezone.localdate()
    except ValueError:
        report_date=timezone.localdate()
    payments_qs=Payment.objects.filter(status="paid",paid_at__date=report_date)
    expenses_qs=Expense.objects.filter(date=report_date)
    apps=Appointment.objects.filter(date=report_date)
    income=_money(payments_qs)
    expense=_money(expenses_qs)
    by_service=list(
        apps.filter(status="done").values("service__name")
        .annotate(n=Count("id"), total=Sum("price_snapshot"))
        .order_by("-n")[:10]
    )
    rating_qs=Rating.objects.filter(appointment__date=report_date)
    rating_avg=rating_qs.aggregate(x=Sum("stars"), n=Count("id"))
    avg_rating=(Decimal(rating_avg["x"])/Decimal(rating_avg["n"])).quantize(Decimal("0.1")) if rating_avg["n"] else None
    payment_methods=[{"key":k,"label":label,"amount":_money(payments_qs.filter(payment_method=k))} for k,label in Payment.METHOD_CHOICES]
    context={
        "report_date":report_date,"income":income,"expense":expense,"net":income-expense,
        "appointment_count":apps.count(),"done_count":apps.filter(status="done").count(),
        "cancelled_count":apps.filter(status="cancelled").count(),
        "rating_count":rating_qs.count(),"avg_rating":avg_rating,
        "by_service":by_service,"payment_methods":payment_methods,
    }
    return render(request,"core/reports.html",context)


@login_required
def assistant(request):
    answer=None
    if request.method=="POST": answer=assistant_answer(request.POST.get("prompt",""))
    return render(request,"core/assistant.html",{"answer":answer})


def assistant_answer(prompt):
    p=(prompt or "").lower(); today=timezone.localdate()
    if any(x in p for x in ["narx","xizmat","price"]):
        items=Service.objects.filter(is_active=True); return "\n".join(f"✂ {x.name} — {x.price:,.0f} so‘m — {x.duration} daqiqa" for x in items) or "Hozircha faol xizmat yo‘q."
    if any(x in p for x in ["bugun","navbat","booking"]):
        apps=Appointment.objects.filter(date=today).count(); return f"Bugun {apps} ta navbat bor."
    if any(x in p for x in ["mijoz","customer"]): return f"CRM’da {Customer.objects.count()} ta mijoz bor."
    if any(x in p for x in ["sartarosh","barber","usta"]): return f"Hozir {Barber.objects.filter(is_active=True).count()} ta faol sartarosh bor."
    if any(x in p for x in ["daromad","to‘lov","tolov","kassa"]): return f"Jami tushum: {_money(Payment.objects.all()):,.0f} so‘m."
    if any(x in p for x in ["xarajat","expense"]): return f"Jami xarajat: {_money(Expense.objects.all()):,.0f} so‘m."
    if any(x in p for x in ["manzil","adres","address"]): return "Sartaroshxona manzilini direktor sozlamalarida kiritish mumkin."
    return "Men Barber Aura yordamchisiman 🤖. Xizmatlar, narxlar, navbatlar, barberlar, mijozlar, daromad va xarajatlar haqida so‘rashingiz mumkin."


@login_required
def profile_link(request):
    return redirect("profile")
