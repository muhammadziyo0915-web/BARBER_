import asyncio, os, json, html, logging, traceback
from pathlib import Path
from datetime import datetime, timedelta, date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ErrorEvent, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile, InputMediaPhoto
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import SendMessage
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from translit import to_cyrillic
from core.models import Customer, Appointment, Service, Barber, BarberTimeOff, Profile, Notification, Rating

TOKEN = settings.TELEGRAM_BOT_TOKEN
bot = Bot(TOKEN) if TOKEN else None
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("barber_bot")

# ---------- Til (lotin / kirill) ----------
LANG_FILE = Path(__file__).resolve().parent / "bot_lang.json"
try: _LANGS = json.loads(LANG_FILE.read_text(encoding="utf-8"))
except Exception: _LANGS = {}

def get_lang(chat_id): return _LANGS.get(str(chat_id), "lat")

def set_lang(chat_id, lang):
    _LANGS[str(chat_id)] = lang
    try: LANG_FILE.write_text(json.dumps(_LANGS, ensure_ascii=False), encoding="utf-8")
    except Exception as exc: print("Til saqlanmadi:", exc)

def _is_lang_menu(markup):
    return isinstance(markup, InlineKeyboardMarkup) and any((b.callback_data or "").startswith("lang:") for row in markup.inline_keyboard for b in row)

def _tr_markup(markup):
    if isinstance(markup, InlineKeyboardMarkup):
        return markup.model_copy(update={"inline_keyboard": [[b.model_copy(update={"text": to_cyrillic(b.text)}) for b in row] for row in markup.inline_keyboard]})
    if isinstance(markup, ReplyKeyboardMarkup):
        return markup.model_copy(update={"keyboard": [[b.model_copy(update={"text": to_cyrillic(b.text)}) for b in row] for row in markup.keyboard]})
    return markup

class CyrillicMiddleware(BaseRequestMiddleware):
    """Foydalanuvchi kirill tanlagan bo'lsa, botning barcha matn va tugmalarini kirillga o'tkazadi."""
    async def __call__(self, make_request, bot, method):
        if isinstance(method, SendMessage) and get_lang(method.chat_id) == "cyr" and not _is_lang_menu(method.reply_markup):
            method = method.model_copy(update={"text": to_cyrillic(method.text), "reply_markup": _tr_markup(method.reply_markup)})
        return await make_request(bot, method)

if bot: bot.session.middleware(CyrillicMiddleware())

class BookingState(StatesGroup):
    service = State(); barber = State(); date = State(); time = State(); name = State(); phone = State(); confirm = State()

@sync_to_async
def link_phone(chat_id: int, phone: str):
    customer = Customer.objects.filter(phone=phone).first()
    if customer:
        customer.telegram_chat_id = str(chat_id); customer.save(update_fields=["telegram_chat_id"])
    linked = bool(customer)
    for p in Profile.objects.filter(phone=phone):
        p.telegram_chat_id = str(chat_id); p.save(update_fields=["telegram_chat_id"]); linked = True
    return str(customer) if customer else ("profilingiz" if linked else None)

@sync_to_async
def upcoming_for_chat(chat_id: int):
    today=timezone.localdate()
    return list(Appointment.objects.filter(customer__telegram_chat_id=str(chat_id),date__gte=today,status__in=["waiting","confirmed","progress"]).select_related("service","barber","customer")[:10])

@sync_to_async
def active_services():
    return list(Service.objects.filter(is_active=True).prefetch_related("images").order_by("name"))

@sync_to_async
def service_info(service_id):
    s=Service.objects.get(pk=service_id,is_active=True)
    return {"id":s.id,"name":s.name,"description":s.description,"price":s.price,"duration":s.duration,"images":[x.image.path for x in s.images.all() if x.image]}

@sync_to_async
def barber_days(barber_id):
    b=Barber.objects.get(pk=barber_id,is_active=True)
    return {x.strip() for x in b.working_days.split(",") if x.strip()}

@sync_to_async
def known_customer(chat_id):
    c=Customer.objects.filter(telegram_chat_id=str(chat_id)).exclude(phone="").order_by("-id").first()
    return (str(c),c.phone) if c else None

@sync_to_async
def booking_summary(service_id,barber_id):
    s=Service.objects.get(pk=service_id); b=Barber.objects.get(pk=barber_id)
    return {"service":s.name,"price":s.price,"duration":s.duration,"barber":str(b)}

@sync_to_async
def active_barbers(service_id=None):
    qs=Barber.objects.filter(is_active=True).select_related("user")
    if service_id and Service.objects.filter(pk=service_id, barbers__isnull=False).exists(): qs=qs.filter(services__id=service_id)
    return list(qs.order_by("user__first_name","user__username"))

@sync_to_async
def available_dates(barber_id, service_id):
    return [timezone.localdate()+timedelta(days=i) for i in range(7)]

@sync_to_async
def available_times(barber_id, service_id, selected_date):
    service=Service.objects.get(pk=service_id,is_active=True); barber=Barber.objects.get(pk=barber_id,is_active=True)
    if not barber.works_on(selected_date): return []
    busy=list(Appointment.objects.filter(barber=barber,date=selected_date,status__in=["waiting","confirmed","progress"]).values_list("start_time","end_time"))
    off=list(BarberTimeOff.objects.filter(barber=barber,date=selected_date).values_list("start_time","end_time"))
    slots=[]; start=datetime.combine(selected_date,barber.work_start); finish=datetime.combine(selected_date,barber.work_end); now=timezone.localtime().replace(tzinfo=None)
    while start+timedelta(minutes=service.duration)<=finish:
        st=start.time(); en=(start+timedelta(minutes=service.duration)).time()
        clash=any(a and b and a < en and b > st for a,b in busy+off)
        future=selected_date>now.date() or (selected_date==now.date() and start>now)
        if future and not clash: slots.append(start.strftime("%H:%M"))
        start+=timedelta(minutes=30)
    return slots

@sync_to_async
@transaction.atomic
def create_booking(chat_id, service_id, barber_id, selected_date, start_time, name, phone):
    service=Service.objects.select_for_update().get(pk=service_id,is_active=True)
    barber=Barber.objects.get(pk=barber_id,is_active=True)
    if barber.services.exists() and not barber.services.filter(pk=service.id).exists(): raise ValueError("Bu xizmatni tanlangan barber bajarmaydi.")
    if not barber.works_on(selected_date): raise ValueError("Bu kuni barber ishlamaydi.")
    first,*last=name.strip().split(); last_name=" ".join(last); st=datetime.strptime(start_time,"%H:%M").time(); end=(datetime.combine(selected_date,st)+timedelta(minutes=service.duration)).time()
    if st<barber.work_start or end>barber.work_end: raise ValueError("Tanlangan vaqt ish jadvaliga kirmaydi.")
    if BarberTimeOff.objects.filter(barber=barber,date=selected_date,start_time__lt=end,end_time__gt=st).exists(): raise ValueError("Bu vaqt barber tomonidan vaqtincha yopilgan.")
    if Appointment.objects.filter(barber=barber,date=selected_date,status__in=["waiting","confirmed","progress"],start_time__lt=end,end_time__gt=st).exists(): raise ValueError("Bu vaqt hozirgina band bo‘lib qoldi. Boshqa vaqtni tanlang.")
    customer,_=Customer.objects.get_or_create(phone=phone,defaults={"first_name":first,"last_name":last_name})
    customer.first_name=first; customer.last_name=last_name; customer.telegram_chat_id=str(chat_id); customer.save(update_fields=["first_name","last_name","telegram_chat_id"])
    ap=Appointment.objects.create(customer=customer,barber=barber,service=service,date=selected_date,start_time=st,end_time=end,status="waiting",price_snapshot=service.price,duration_snapshot=service.duration)
    profiles=list(Profile.objects.filter(role="director"))+list(Profile.objects.filter(user=barber.user))
    msg=f"🔔 <b>Yangi navbat!</b>\n👤 {html.escape(str(customer))}\n💈 {html.escape(str(barber))}\n✂ {html.escape(service.name)}\n📅 {selected_date:%d.%m.%Y}\n🕐 {st:%H:%M}–{end:%H:%M}\n💰 {service.price:,.0f} so‘m"
    for p in {x.pk:x for x in profiles}.values():
        if p.telegram_chat_id: Notification.objects.create(recipient=p,appointment=ap,message=msg)
    return ap.id,service.name,str(barber),service.price

@sync_to_async
def notifications_due():
    return list(Notification.objects.filter(sent=False).select_related("recipient"))[:30]

@sync_to_async
def mark_notification(pk): Notification.objects.filter(pk=pk).update(sent=True)

@sync_to_async
def reminders_due():
    now=timezone.localtime(); result=[]
    for ap in Appointment.objects.filter(date=now.date(),status__in=["waiting","confirmed"],reminder_sent=False).select_related("customer","service","barber"):
        target=timezone.make_aware(datetime.combine(ap.date,ap.start_time),timezone.get_current_timezone()); minutes=ap.customer.notify_minutes or settings.TELEGRAM_REMINDER_MINUTES
        if timedelta(0)<=target-now<=timedelta(minutes=minutes): result.append(ap)
    return result

@sync_to_async
def mark_reminded(pk): Appointment.objects.filter(pk=pk).update(reminder_sent=True)

@sync_to_async
def ratings_due():
    return list(
        Appointment.objects.filter(
            status="done", rating_sent=False, customer__telegram_chat_id__isnull=False
        ).exclude(customer__telegram_chat_id="").select_related("customer","barber","service").order_by("date","start_time")[:20]
    )

@sync_to_async
def mark_rating_sent(pk):
    Appointment.objects.filter(pk=pk).update(rating_sent=True)

@sync_to_async
def save_rating(chat_id, appointment_id, stars):
    ap=Appointment.objects.filter(
        pk=appointment_id, status="done", customer__telegram_chat_id=str(chat_id)
    ).first()
    if not ap:
        return False
    if Rating.objects.filter(appointment=ap).exists():
        return True
    Rating.objects.create(appointment=ap, stars=stars)
    ap.rating_sent=True
    ap.save(update_fields=["rating_sent"])
    return True

def service_kb(items): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✂ {x.name} — {x.price:,.0f} so‘m",callback_data=f"svc:{x.id}")] for x in items])
def style_kb(items): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✂ {x.name} — {x.price:,.0f} so‘m",callback_data=f"style:{x.id}")] for x in items])
def barber_kb(items):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💈 {str(x)}",callback_data=f"bar:{x.id}")] for x in items])
WD=["Du","Se","Chor","Pay","Ju","Sha","Yak"]
e=html.escape
def nav_row(back=None):
    row=[]
    if back: row.append(InlineKeyboardButton(text="⬅️ Orqaga",callback_data=f"back:{back}"))
    row.append(InlineKeyboardButton(text="🏠 Menyu",callback_data="home"))
    return row
def with_nav(markup,back=None): return InlineKeyboardMarkup(inline_keyboard=list(markup.inline_keyboard)+[nav_row(back)])
def date_kb(workdays=None):
    btns=[]; today=timezone.localdate()
    for i in range(21):
        d=today+timedelta(days=i)
        if workdays is not None and str(d.weekday()) not in workdays: continue
        label="Bugun" if i==0 else ("Ertaga" if i==1 else WD[d.weekday()])
        btns.append(InlineKeyboardButton(text=f"📅 {label} · {d:%d.%m}",callback_data=f"date:{d.isoformat()}"))
        if len(btns)>=8: break
    return InlineKeyboardMarkup(inline_keyboard=[btns[k:k+2] for k in range(0,len(btns),2)])
def time_kb(slots): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🕐 {x}",callback_data=f"time:{x}") for x in slots[i:i+3]] for i in range(0,len(slots),3)])
def contact_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Telefon raqamimni yuborish",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)

def home_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📅 Navbat olish",callback_data="book:start")],[InlineKeyboardButton(text="✂️ Soch stillari",callback_data="styles")],[InlineKeyboardButton(text="💈 Barberlar",callback_data="barbers")],[InlineKeyboardButton(text="📋 Mening navbatlarim",callback_data="my:apps")],[InlineKeyboardButton(text="🤖 Mini yordamchi",callback_data="minihelp")]])

def lang_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇺🇿 O‘zbekcha",callback_data="lang:lat"),InlineKeyboardButton(text="🇺🇿 Ўзбекча",callback_data="lang:cyr")]])
def start_reply_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Start")]],resize_keyboard=True)

@dp.message(Command("start"))
async def start(message:Message,state:FSMContext):
    await state.clear()
    await message.answer("🌐 <b>Tilni tanlang / Тилни танланг</b>",reply_markup=lang_kb(),parse_mode="HTML")

@dp.callback_query(F.data.startswith("lang:"))
async def choose_language(call:CallbackQuery,state:FSMContext):
    await call.answer(); await state.clear(); set_lang(call.message.chat.id,call.data.split(":")[1]); name=call.from_user.first_name or "mehmon"
    await call.message.answer(f"✂️ <b>BARBER AURA</b> ga xush kelibsiz, {name}! 👋\n\n💈 Zamonaviy stillar, professional barberlar va qulay navbat — barchasi shu yerda.\n\nQuyidan kerakli bo‘limni tanlang 👇",reply_markup=home_kb(),parse_mode="HTML")

@dp.message(F.text.in_({"🏠 Start","🏠 Старт"}))
async def start_button(message:Message,state:FSMContext):
    await state.clear(); await message.answer("🏠 <b>Bosh menyu</b>\n\nKerakli bo‘limni tanlang 👇",reply_markup=home_kb(),parse_mode="HTML")

@dp.callback_query(F.data=="styles")
async def styles(call:CallbackQuery):
    try: await call.answer()
    except Exception: pass
    items=await active_services()
    if not items:
        await call.message.answer("Hozircha faol soch stillari yo‘q.",reply_markup=home_kb()); return
    await call.message.answer("✂️ <b>Soch stillari va xizmatlar</b>\n\nKerakli stilni tanlang:",reply_markup=with_nav(style_kb(items)),parse_mode="HTML")

@dp.callback_query(F.data.startswith("style:"))
async def service_detail(call:CallbackQuery,state:FSMContext):
    # "query is too old" xatosi butun handlerni to'xtatib qo'ymasin
    try: await call.answer()
    except Exception as exc: log.warning("call.answer: %s",exc)
    sid=int(call.data.split(":")[1])
    try: s=await service_info(sid)
    except Exception:
        log.exception("service_info(%s) xato",sid)
        await call.message.answer("❌ Bu xizmat topilmadi yoki o‘chirilgan.",reply_markup=home_kb()); return
    # HTML belgilari (&, <, >) Telegramda xato bermasligi uchun escape qilinadi
    name=html.escape(s["name"] or ""); desc=html.escape(s["description"] or "Professional sartarosh xizmati.")
    text=f"✂️ <b>{name}</b>\n\n{desc}\n\n💰 <b>{s['price']:,.0f} so‘m</b>\n⏱️ <b>{s['duration']} daqiqa</b>"
    paths=[p for p in s["images"][:10] if os.path.exists(p)]
    missing=[p for p in s["images"][:10] if not os.path.exists(p)]
    if missing: log.warning("Rasm fayli topilmadi: %s",missing)
    # 1) Rasmlar (xato bo'lsa ham matn baribir chiqadi)
    if len(paths)>=2:
        try: await call.message.answer_media_group([InputMediaPhoto(media=FSInputFile(p)) for p in paths])
        except Exception:
            log.exception("Albom yuborilmadi, bittalab yuboriladi")
            for p in paths:
                try: await call.message.answer_photo(FSInputFile(p))
                except Exception: log.exception("Rasm yuborilmadi: %s",p)
    elif len(paths)==1:
        try: await call.message.answer_photo(FSInputFile(paths[0]))
        except Exception: log.exception("Rasm yuborilmadi: %s",paths[0])
    # 2) Matn + tugma — har doim chiqadi
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Shu stilni tanlash",callback_data=f"choose:{sid}")],nav_row("styles")])
    try: await call.message.answer(text,reply_markup=kb,parse_mode="HTML")
    except Exception:
        log.exception("HTML matn yuborilmadi, oddiy matn yuboriladi")
        await call.message.answer(f"{s['name']}\n\n{s['description'] or ''}\n\n💰 {s['price']:,.0f} so‘m\n⏱️ {s['duration']} daqiqa",reply_markup=kb)

@dp.callback_query(F.data.startswith("choose:"))
async def choose_service(call:CallbackQuery,state:FSMContext):
    await call.answer(); sid=int(call.data.split(":")[1]); await state.update_data(service_id=sid); bars=await active_barbers(sid)
    if not bars: await call.message.answer("❌ Bu xizmatni bajaradigan faol barber topilmadi."); return
    await state.set_state(BookingState.barber); await call.message.answer("1️⃣ <b>Sartaroshni tanlang:</b>",reply_markup=with_nav(barber_kb(bars),"service"),parse_mode="HTML")

@dp.callback_query(F.data=="book:start")
async def book_start(call:CallbackQuery,state:FSMContext):
    await call.answer(); items=await active_services(); await state.set_state(BookingState.service); await call.message.answer("1️⃣ <b>Xizmatni tanlang:</b>",reply_markup=with_nav(service_kb(items)),parse_mode="HTML")

@dp.callback_query(BookingState.service,F.data.startswith("svc:"))
async def choose_service_from_book(call:CallbackQuery,state:FSMContext): await choose_service(call,state)

@dp.callback_query(BookingState.barber,F.data.startswith("bar:"))
async def choose_barber(call:CallbackQuery,state:FSMContext):
    await call.answer(); bid=int(call.data.split(":")[1]); wd=await barber_days(bid)
    await state.update_data(barber_id=bid,workdays=sorted(wd)); await state.set_state(BookingState.date)
    await call.message.answer("2️⃣ <b>Sanani tanlang:</b>",reply_markup=with_nav(date_kb(wd),"barber"),parse_mode="HTML")

@dp.callback_query(BookingState.date,F.data.startswith("date:"))
async def choose_date(call:CallbackQuery,state:FSMContext):
    await call.answer(); selected=date.fromisoformat(call.data.split(":",1)[1]); data=await state.get_data(); slots=await available_times(data["barber_id"],data["service_id"],selected)
    wd=set(data["workdays"]) if data.get("workdays") else None
    if not slots: await call.message.answer("❌ Bu kunda bo‘sh vaqt yo‘q. Boshqa sana tanlang.",reply_markup=with_nav(date_kb(wd),"barber")); return
    await state.update_data(selected_date=selected.isoformat()); await state.set_state(BookingState.time)
    await call.message.answer(f"3️⃣ <b>Bo‘sh vaqtni tanlang</b> ({selected:%d.%m.%Y}):",reply_markup=with_nav(time_kb(slots),"date"),parse_mode="HTML")

@dp.callback_query(BookingState.time,F.data.startswith("time:"))
async def choose_time(call:CallbackQuery,state:FSMContext):
    await call.answer(); await state.update_data(start_time=call.data.split(":",1)[1]); await state.set_state(BookingState.name)
    known=await known_customer(call.message.chat.id)
    if known:
        await state.update_data(known_name=known[0],known_phone=known[1])
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ha, shu ma’lumot bilan",callback_data="reuse:yes")],[InlineKeyboardButton(text="✏️ Boshqa ma’lumot kiritish",callback_data="reuse:no")],nav_row("time")])
        await call.message.answer(f"4️⃣ <b>Oldingi ma’lumotlaringiz bilan davom etamizmi?</b>\n\n👤 {e(known[0])}\n📱 {e(known[1])}",reply_markup=kb,parse_mode="HTML"); return
    await call.message.answer("4️⃣ <b>Ism va familiyangizni yozing:</b>",reply_markup=ReplyKeyboardRemove(),parse_mode="HTML")

@dp.callback_query(BookingState.name,F.data=="reuse:yes")
async def reuse_yes(call:CallbackQuery,state:FSMContext):
    await call.answer(); d=await state.get_data(); await state.update_data(name=d["known_name"],phone=d["known_phone"]); await show_confirm(call.message,state)

@dp.callback_query(BookingState.name,F.data=="reuse:no")
async def reuse_no(call:CallbackQuery,state:FSMContext):
    await call.answer(); await call.message.answer("4️⃣ <b>Ism va familiyangizni yozing:</b>",reply_markup=ReplyKeyboardRemove(),parse_mode="HTML")

@dp.message(BookingState.name)
async def choose_name(message:Message,state:FSMContext):
    name=(message.text or "").strip()
    if len(name)<2: await message.answer("Iltimos, ism-familiyangizni yozing."); return
    await state.update_data(name=name); await state.set_state(BookingState.phone); await message.answer("5️⃣ <b>Telefon raqamingizni yuboring:</b>",reply_markup=contact_kb(),parse_mode="HTML")

@dp.message(BookingState.phone,F.contact)
async def choose_contact(message:Message,state:FSMContext): await state.update_data(phone=message.contact.phone_number); await show_confirm(message,state)
@dp.message(BookingState.phone)
async def choose_phone_text(message:Message,state:FSMContext):
    phone=(message.text or "").strip()
    if len(phone)<7: await message.answer("Telefon raqamini to‘g‘ri kiriting.",reply_markup=contact_kb()); return
    await state.update_data(phone=phone); await show_confirm(message,state)

async def show_confirm(message,state):
    d=await state.get_data(); sm=await booking_summary(d["service_id"],d["barber_id"]); selected=date.fromisoformat(d["selected_date"]); await state.set_state(BookingState.confirm)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiqlash",callback_data="confirm:yes")],[InlineKeyboardButton(text="❌ Bekor qilish",callback_data="home")]])
    await message.answer(f"📝 <b>Ma’lumotlarni tekshiring</b>\n\n✂ {e(sm['service'])}\n💈 {e(sm['barber'])}\n📅 {selected:%d.%m.%Y}\n🕐 {d['start_time']}\n⏱ {sm['duration']} daqiqa\n💰 {sm['price']:,.0f} so‘m\n\n👤 {e(d['name'])}\n📱 {e(d['phone'])}",reply_markup=kb,parse_mode="HTML")

@dp.callback_query(BookingState.confirm,F.data=="confirm:yes")
async def confirm_yes(call:CallbackQuery,state:FSMContext):
    await call.answer(); d=await state.get_data(); await finish_booking(call.message,state,d["phone"])

async def finish_booking(message,state,phone):
    data=await state.get_data()
    try:
        selected=date.fromisoformat(data["selected_date"]); ap_id,service,barber,price=await create_booking(message.chat.id,data["service_id"],data["barber_id"],selected,data["start_time"],data["name"],phone)
    except Exception as exc: await message.answer(f"❌ Navbat yaratilmadi: {exc}",reply_markup=start_reply_kb()); await state.clear(); return
    await state.clear(); await message.answer(f"✅ <b>Navbatingiz qabul qilindi!</b>\n\n🆔 #{ap_id}\n✂ {e(service)}\n💈 {e(barber)}\n📅 {selected:%d.%m.%Y}\n🕐 {data['start_time']}\n💰 {price:,.0f} so‘m\n\n🔔 Direktor va barberga bildirishnoma yuborildi.\n\nYana navbat olish uchun pastdagi «🏠 Start» tugmasini bosing 👇",reply_markup=start_reply_kb(),parse_mode="HTML")

@dp.callback_query(F.data=="my:apps")
async def my_apps(call:CallbackQuery):
    await call.answer(); apps=await upcoming_for_chat(call.message.chat.id)
    if not apps: await call.message.answer("Sizda yaqin navbatlar yo‘q. 📅 Navbat olish tugmasidan foydalaning.",reply_markup=home_kb()); return
    for a in apps:
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish",callback_data=f"cancel:{a.id}")]])
        await call.message.answer(f"📅 <b>#{a.id}</b>\n✂ {e(a.service.name)}\n💈 {e(str(a.barber))}\n🗓 {a.date:%d.%m.%Y}\n🕐 {a.start_time:%H:%M}–{a.end_time:%H:%M}\n💰 {a.price_snapshot:,.0f} so‘m",reply_markup=kb,parse_mode="HTML")

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_booking(call:CallbackQuery):
    await call.answer(); aid=int(call.data.split(":")[1]); ap=await cancel_for_chat(call.message.chat.id,aid); await call.message.answer("✅ Navbat bekor qilindi." if ap else "❌ Navbat topilmadi yoki uni bekor qilib bo‘lmaydi.")

@sync_to_async
def cancel_for_chat(chat_id,aid):
    ap=Appointment.objects.filter(pk=aid,customer__telegram_chat_id=str(chat_id),status__in=["waiting","confirmed"]).select_related("barber","customer").first()
    if not ap:return False
    ap.status="cancelled"; ap.save(update_fields=["status"])
    for p in list(Profile.objects.filter(role="director"))+list(Profile.objects.filter(user=ap.barber.user)):
        if p.telegram_chat_id: Notification.objects.create(recipient=p,appointment=ap,message=f"❌ Navbat bekor qilindi!\n👤 {html.escape(str(ap.customer))}\n💈 {html.escape(str(ap.barber))}\n📅 {ap.date:%d.%m.%Y} {ap.start_time:%H:%M}")
    return True

@dp.callback_query(F.data.startswith("rate:"))
async def rate_service(call:CallbackQuery):
    await call.answer()
    try:
        _, aid, stars = call.data.split(":")
        stars=int(stars)
        if stars < 1 or stars > 5:
            raise ValueError
    except ValueError:
        await call.message.answer("❌ Baho noto‘g‘ri.")
        return
    ok=await save_rating(call.message.chat.id,int(aid),stars)
    await call.message.answer("⭐ Rahmat! Bahoyingiz saqlandi." if ok else "❌ Bu baholashga ruxsat yo‘q yoki navbat topilmadi.")

@dp.callback_query(F.data=="barbers")
async def barbers_cmd(call:CallbackQuery):
    await call.answer(); bars=await active_barbers()
    if not bars: await call.message.answer("Hozircha faol barber yo‘q.",reply_markup=home_kb()); return
    await call.message.answer("💈 <b>Bizning barberlar</b>",parse_mode="HTML")
    for b in bars:
        cap=f"💈 <b>{e(str(b))}</b>\n{e(b.specialization or 'Professional barber')}\n🎖 Tajriba: {b.experience} yil\n🕐 {b.work_start:%H:%M}–{b.work_end:%H:%M}"
        sent=False
        try:
            if b.photo and os.path.exists(b.photo.path): await call.message.answer_photo(FSInputFile(b.photo.path),caption=cap,parse_mode="HTML"); sent=True
        except Exception: log.exception("Barber rasmi yuborilmadi")
        if not sent: await call.message.answer(cap,parse_mode="HTML")
    await call.message.answer("Navbat olish uchun 👇",reply_markup=home_kb())

@dp.callback_query(F.data=="minihelp")
async def minihelp(call:CallbackQuery): await call.answer(); await call.message.answer("🤖 Men xizmatlar, narxlar, bo‘sh vaqtlar, barberlar va navbatlar haqida yordam beraman. Masalan: <i>Fade narxi qancha?</i>",parse_mode="HTML")

@dp.message(Command("link"))
async def link(message:Message):
    parts=message.text.split(maxsplit=1)
    if len(parts)<2: await message.answer("Telefoningizni yuboring: /link +998901234567"); return
    customer=await link_phone(message.chat.id,parts[1].strip()); await message.answer("✅ Telegram profilingiz bog‘landi." if customer else "❌ Bu telefon CRMda topilmadi.")

@dp.message(Command("book"))
async def book_command(message:Message,state:FSMContext): await state.clear(); await state.set_state(BookingState.service); await message.answer("1️⃣ <b>Xizmatni tanlang:</b>",reply_markup=service_kb(await active_services()),parse_mode="HTML")
@dp.message(Command("myappointments"))
async def my_appointments(message:Message):
    apps=await upcoming_for_chat(message.chat.id)
    await message.answer("Yaqin navbatlaringiz yo‘q." if not apps else "\n".join(f"#{a.id} — {a.date:%d.%m.%Y} {a.start_time:%H:%M} — {a.service.name} — {a.barber}" for a in apps))
@dp.message(Command("help"))
async def help_cmd(message:Message): await message.answer("/start — bosh menyu\n/book — navbat olish\n/myappointments — navbatlar\n/link +998... — Telegramni CRM bilan bog‘lash")

@dp.callback_query(F.data=="home")
async def go_home(call:CallbackQuery,state:FSMContext):
    await call.answer(); await state.clear(); await call.message.answer("🏠 <b>Bosh menyu</b>\n\nKerakli bo‘limni tanlang 👇",reply_markup=home_kb(),parse_mode="HTML")

@dp.callback_query(F.data.startswith("back:"))
async def go_back(call:CallbackQuery,state:FSMContext):
    await call.answer(); step=call.data.split(":")[1]; d=await state.get_data(); m=call.message
    if step=="styles":
        items=await active_services(); await m.answer("✂️ <b>Soch stillari va xizmatlar</b>\n\nKerakli stilni tanlang:",reply_markup=with_nav(style_kb(items)),parse_mode="HTML"); return
    if step=="barber" and d.get("service_id"):
        bars=await active_barbers(d["service_id"]); await state.set_state(BookingState.barber); await m.answer("1️⃣ <b>Sartaroshni tanlang:</b>",reply_markup=with_nav(barber_kb(bars),"service"),parse_mode="HTML"); return
    if step=="date" and d.get("barber_id"):
        wd=set(d["workdays"]) if d.get("workdays") else None; await state.set_state(BookingState.date); await m.answer("2️⃣ <b>Sanani tanlang:</b>",reply_markup=with_nav(date_kb(wd),"barber"),parse_mode="HTML"); return
    if step=="time" and d.get("selected_date"):
        slots=await available_times(d["barber_id"],d["service_id"],date.fromisoformat(d["selected_date"]))
        if slots: await state.set_state(BookingState.time); await m.answer("3️⃣ <b>Bo‘sh vaqtni tanlang:</b>",reply_markup=with_nav(time_kb(slots),"date"),parse_mode="HTML"); return
    items=await active_services(); await state.set_state(BookingState.service); await m.answer("1️⃣ <b>Xizmatni tanlang:</b>",reply_markup=with_nav(service_kb(items)),parse_mode="HTML")

@dp.errors()
async def on_error(event:ErrorEvent):
    log.error("Handler xatosi: %s\n%s",event.exception,"".join(traceback.format_exception(event.exception)))
    upd=event.update
    try:
        target=upd.callback_query.message if upd.callback_query else (upd.message if upd.message else None)
        if target: await target.answer("⚠️ Kutilmagan xato yuz berdi. Iltimos, /start ni bosib qayta urinib ko‘ring.")
    except Exception: pass
    return True

async def notification_loop():
    while True:
        try:
            if bot:
                for n in await notifications_due():
                    chat=n.recipient.telegram_chat_id
                    if chat:
                        try: await bot.send_message(int(chat),n.message,parse_mode="HTML")
                        except Exception as exc: print("Notification error:",exc)
                    await mark_notification(n.pk)
        except Exception as exc: print("Notification loop:",exc)
        await asyncio.sleep(4)

async def rating_loop():
    while True:
        try:
            if bot:
                for ap in await ratings_due():
                    chat=int(ap.customer.telegram_chat_id)
                    kb=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="⭐ 1",callback_data=f"rate:{ap.id}:1"),
                         InlineKeyboardButton(text="⭐ 2",callback_data=f"rate:{ap.id}:2"),
                         InlineKeyboardButton(text="⭐ 3",callback_data=f"rate:{ap.id}:3"),
                         InlineKeyboardButton(text="⭐ 4",callback_data=f"rate:{ap.id}:4"),
                         InlineKeyboardButton(text="⭐ 5",callback_data=f"rate:{ap.id}:5")]
                    ])
                    await bot.send_message(
                        chat,
                        f"✨ <b>Xizmatimiz sizga qanday yoqdi?</b>\n\n✂ {e(ap.service.name)}\n💈 {e(str(ap.barber))}\n\n1 dan 5 gacha baholang:",
                        reply_markup=kb, parse_mode="HTML"
                    )
                    await mark_rating_sent(ap.id)
        except Exception as exc:
            print("Rating loop:",exc)
        await asyncio.sleep(20)

async def reminder_loop():
    while True:
        try:
            if bot:
                for ap in await reminders_due():
                    if ap.customer.telegram_chat_id:
                        await bot.send_message(int(ap.customer.telegram_chat_id),f"⏰ <b>Navbatingiz yaqin!</b>\n\n✂ {ap.service.name}\n💈 {ap.barber}\n📅 {ap.date:%d.%m.%Y}\n🕐 {ap.start_time:%H:%M}\n\nIltimos, vaqtida yetib keling. ✨",parse_mode="HTML")
                    await mark_reminded(ap.pk)
        except Exception as exc: print("Reminder error:",exc)
        await asyncio.sleep(30)

async def main():
    if not TOKEN or TOKEN.startswith("PASTE_"): print("TELEGRAM_BOT_TOKEN .env faylda kiritilmagan."); return
    print("BARBER AURA Telegram bot ishga tushdi..."); await asyncio.gather(dp.start_polling(bot),notification_loop(),reminder_loop(),rating_loop())

if __name__=="__main__": asyncio.run(main())
