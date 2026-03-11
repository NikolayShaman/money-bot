#!/usr/bin/env python3
"""💰 Бот-аффирмации денежных поступлений"""

import asyncio, random, json, os, logging
from datetime import datetime, date, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

(MENU, EDIT_TEXT, EDIT_AMOUNT_MIN, EDIT_AMOUNT_MAX,
 EDIT_T1_TIME, EDIT_T1_END, EDIT_T2_TIME, EDIT_T2_END) = range(8)

SETTINGS_FILE = "bot_settings.json"

CURRENCIES = {"RUB": "₽", "USD": "$", "THB": "฿"}
FREQUENCY_OPTIONS = {
    "1": "каждый день", "2": "раз в 2 дня", "3": "раз в 3 дня",
    "4": "раз в 4 дня", "5": "раз в 5 дней", "6": "раз в 6 дней",
}
TIMEZONES = {
    "TH":  ("🇹🇭 Таиланд UTC+7",       "Asia/Bangkok"),
    "RU3": ("🇷🇺 Москва UTC+3",         "Europe/Moscow"),
    "RU5": ("🇷🇺 Екатеринбург UTC+5",   "Asia/Yekaterinburg"),
    "RU7": ("🇷🇺 Новосибирск UTC+7",    "Asia/Novosibirsk"),
    "RU10":("🇷🇺 Владивосток UTC+10",   "Asia/Vladivostok"),
    "CN":  ("🇨🇳 Китай UTC+8",          "Asia/Shanghai"),
    "AE":  ("🇦🇪 Дубай UTC+4",          "Asia/Dubai"),
    "EU":  ("🇪🇺 Европа UTC+1",         "Europe/Berlin"),
    "US":  ("🇺🇸 Нью-Йорк UTC-5",       "America/New_York"),
}


def load_settings(user_id):
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(str(user_id), {})
    return {}

def save_settings(user_id, settings):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[str(user_id)] = settings
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_now(settings):
    tz_key = settings.get("timezone", "TH")
    tz_str = TIMEZONES.get(tz_key, ("", "Asia/Bangkok"))[1]
    return datetime.now(pytz.timezone(tz_str))

def format_amount(amount, currency):
    sym = CURRENCIES.get(currency, currency)
    if currency == "USD":
        return f"{sym}{amount:,.2f}"
    return f"{round(amount):,} {sym}".replace(",", " ")

def generate_notification(settings):
    amount = random.uniform(float(settings.get("amount_min", 1000)), float(settings.get("amount_max", 10000)))
    currency = settings.get("currency", "RUB")
    if currency == "RUB": amount = round(amount / 100) * 100
    elif currency == "USD": amount = round(amount, 2)
    elif currency == "THB": amount = round(amount / 50) * 50
    now = get_user_now(settings).strftime("%d.%m.%Y %H:%M")
    return (
        f"💰 *Поступление средств*\n\n"
        f"📋 {settings.get('text', 'Поступление')}\n"
        f"💵 Сумма: *{format_amount(amount, currency)}*\n"
        f"🕐 {now}\n\n✅ Средства зачислены на ваш счёт"
    )

def get_random_time(start, end):
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    total1, total2 = h1*60+m1, h2*60+m2
    if total2 < total1: total2 += 24*60
    chosen = random.randint(total1, total2) % (24*60)
    return f"{chosen//60:02d}:{chosen%60:02d}"

def valid_time(t):
    try:
        p = t.strip().split(":")
        return len(p) == 2 and 0 <= int(p[0]) <= 23 and 0 <= int(p[1]) <= 59
    except: return False

def tz_label(settings):
    tz_key = settings.get("timezone", "TH")
    return TIMEZONES.get(tz_key, ("🇹🇭 Таиланд UTC+7",))[0]

def settings_text(settings):
    if not settings:
        return "⚠️ Настройки не заданы"
    sym = CURRENCIES.get(settings.get("currency", "RUB"), "")
    freq = FREQUENCY_OPTIONS.get(str(settings.get("frequency", 1)), "каждый день")
    t1 = settings.get("time1", {})
    t2 = settings.get("time2")
    t1_str = t1.get("value") if t1.get("type") == "exact" else f"{t1.get('start')}–{t1.get('end')}"
    t2_str = ""
    if t2:
        t2v = t2.get("value") if t2.get("type") == "exact" else f"{t2.get('start')}–{t2.get('end')}"
        t2_str = f"\n⏰ Время 2: *{t2v}*"
    status = "🟢 Активен" if settings.get("active") else "🔴 Остановлен"
    now = get_user_now(settings).strftime("%H:%M")
    return (
        f"📊 *Текущие настройки:*\n\n"
        f"🌍 Часовой пояс: {tz_label(settings)}\n"
        f"🕐 Сейчас у тебя: *{now}*\n\n"
        f"📝 Текст: {settings.get('text', '—')}\n"
        f"💵 Сумма: {settings.get('amount_min','—')}–{settings.get('amount_max','—')} {sym}\n"
        f"📅 Периодичность: {freq}\n"
        f"⏰ Время 1: *{t1_str or '—'}*{t2_str}\n"
        f"🔔 Статус: {status}"
    )


# ===== ГЛАВНОЕ МЕНЮ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = load_settings(user_id)
    active = settings.get("active", False)

    if not settings:
        keyboard = [[InlineKeyboardButton("⚙️ Настроить бота", callback_data="full_setup")]]
        text = "💰 *Бот денежных аффирмаций*\n\nНастрой бота чтобы начать!"
    else:
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить настройки", callback_data="edit_menu")],
            [InlineKeyboardButton("⏹ Остановить" if active else "▶️ Запустить", callback_data="toggle")],
            [InlineKeyboardButton("🔔 Тест уведомления", callback_data="test_notify")],
        ]
        text = settings_text(settings)

    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MENU


# ===== МЕНЮ РЕДАКТИРОВАНИЯ =====

async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🌍 Часовой пояс", callback_data="edit_tz"),
         InlineKeyboardButton("📝 Текст", callback_data="edit_text")],
        [InlineKeyboardButton("💵 Сумма", callback_data="edit_amount"),
         InlineKeyboardButton("💱 Валюта", callback_data="edit_currency")],
        [InlineKeyboardButton("📅 Периодичность", callback_data="edit_freq"),
         InlineKeyboardButton("⏰ Время 1", callback_data="edit_time1")],
        [InlineKeyboardButton("⏰ Время 2", callback_data="edit_time2")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ]
    await query.edit_message_text(
        "*Что хочешь изменить?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return MENU


# ===== КНОПКИ =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back_main":
        return await start(update, context)

    if data == "edit_menu":
        return await edit_menu(update, context)

    if data == "toggle":
        settings = load_settings(user_id)
        settings["active"] = not settings.get("active", False)
        save_settings(user_id, settings)
        return await start(update, context)

    if data == "test_notify":
        settings = load_settings(user_id)
        await query.message.reply_text(generate_notification(settings), parse_mode="Markdown")
        return MENU

    if data in ("full_setup", "edit_text"):
        context.user_data["edit_mode"] = "text_only" if data == "edit_text" else "full"
        await query.edit_message_text("📝 Введи текст уведомления:\nНапример: _Перевод от клиента_", parse_mode="Markdown")
        return EDIT_TEXT

    if data == "edit_amount":
        context.user_data["edit_mode"] = "amount_only"
        await query.edit_message_text("💵 Введи *минимальную* сумму (число):\nНапример: `5000`", parse_mode="Markdown")
        return EDIT_AMOUNT_MIN

    if data == "edit_tz":
        rows = []
        keys = list(TIMEZONES.keys())
        for i in range(0, len(keys), 2):
            row = []
            for k in keys[i:i+2]:
                row.append(InlineKeyboardButton(TIMEZONES[k][0], callback_data=f"set_tz_{k}"))
            rows.append(row)
        rows.append([InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")])
        await query.edit_message_text("🌍 Выбери свой часовой пояс:", reply_markup=InlineKeyboardMarkup(rows))
        return MENU

    if data.startswith("set_tz_"):
        tz_key = data[7:]
        settings = load_settings(user_id)
        settings["timezone"] = tz_key
        save_settings(user_id, settings)
        label = TIMEZONES.get(tz_key, ("",))[0]
        now = get_user_now(settings).strftime("%H:%M")
        await query.edit_message_text(f"✅ Часовой пояс: *{label}*\nСейчас у тебя: *{now}*\n\nНапиши /start", parse_mode="Markdown")
        return MENU

    if data == "edit_currency":
        await query.edit_message_text(
            "💱 Выбери валюту:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇷🇺 Рубли ₽", callback_data="set_cur_RUB")],
                [InlineKeyboardButton("🇺🇸 Доллары $", callback_data="set_cur_USD")],
                [InlineKeyboardButton("🇹🇭 Тайские баты ฿", callback_data="set_cur_THB")],
                [InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")],
            ])
        )
        return MENU

    if data.startswith("set_cur_"):
        currency = data[8:]
        settings = load_settings(user_id)
        settings["currency"] = currency
        save_settings(user_id, settings)
        await query.edit_message_text(f"✅ Валюта: *{currency}* {CURRENCIES[currency]}\n\nНапиши /start", parse_mode="Markdown")
        return MENU

    if data == "edit_freq":
        await query.edit_message_text(
            "📅 Выбери периодичность:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Каждый день", callback_data="set_freq_1")],
                [InlineKeyboardButton("Раз в 2 дня", callback_data="set_freq_2"),
                 InlineKeyboardButton("Раз в 3 дня", callback_data="set_freq_3")],
                [InlineKeyboardButton("Раз в 4 дня", callback_data="set_freq_4"),
                 InlineKeyboardButton("Раз в 5 дней", callback_data="set_freq_5")],
                [InlineKeyboardButton("Раз в 6 дней", callback_data="set_freq_6")],
                [InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")],
            ])
        )
        return MENU

    if data.startswith("set_freq_"):
        freq = data[9:]
        settings = load_settings(user_id)
        settings["frequency"] = int(freq)
        settings["next_send_date"] = None
        settings["scheduled_times_today"] = []
        save_settings(user_id, settings)
        await query.edit_message_text(f"✅ Периодичность: *{FREQUENCY_OPTIONS[freq]}*\n\nНапиши /start", parse_mode="Markdown")
        return MENU

    if data == "edit_time1":
        await query.edit_message_text(
            "⏰ *Время уведомления 1* — выбери тип:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Точное время", callback_data="t1_exact")],
                [InlineKeyboardButton("🎲 Диапазон (случайное)", callback_data="t1_range")],
                [InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")],
            ]), parse_mode="Markdown"
        )
        return MENU

    if data == "edit_time2":
        await query.edit_message_text(
            "⏰ *Время уведомления 2* — выбери тип:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Точное время", callback_data="t2_exact")],
                [InlineKeyboardButton("🎲 Диапазон (случайное)", callback_data="t2_range")],
                [InlineKeyboardButton("❌ Убрать время 2", callback_data="remove_time2")],
                [InlineKeyboardButton("◀️ Назад", callback_data="edit_menu")],
            ]), parse_mode="Markdown"
        )
        return MENU

    if data == "remove_time2":
        settings = load_settings(user_id)
        settings["time2"] = None
        save_settings(user_id, settings)
        await query.edit_message_text("✅ Время 2 убрано!\n\nНапиши /start")
        return MENU

    if data == "t1_exact":
        context.user_data["t1_type"] = "exact"
        settings = load_settings(user_id)
        now = get_user_now(settings).strftime("%H:%M")
        await query.edit_message_text(f"⏰ Введи точное время (сейчас у тебя *{now}*):\nФормат: `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T1_TIME

    if data == "t1_range":
        context.user_data["t1_type"] = "range"
        settings = load_settings(user_id)
        now = get_user_now(settings).strftime("%H:%M")
        await query.edit_message_text(f"⏰ Введи *начало* диапазона (сейчас у тебя *{now}*):\nФормат: `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T1_TIME

    if data == "t2_exact":
        context.user_data["t2_type"] = "exact"
        settings = load_settings(user_id)
        now = get_user_now(settings).strftime("%H:%M")
        await query.edit_message_text(f"⏰ Введи точное время 2 (сейчас у тебя *{now}*):\nФормат: `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T2_TIME

    if data == "t2_range":
        context.user_data["t2_type"] = "range"
        settings = load_settings(user_id)
        now = get_user_now(settings).strftime("%H:%M")
        await query.edit_message_text(f"⏰ Введи *начало* диапазона 2 (сейчас у тебя *{now}*):\nФормат: `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T2_TIME

    return MENU


# ===== ВВОД ТЕКСТА =====

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    settings = load_settings(user_id)
    if not settings:
        settings = {"currency": "THB", "amount_min": 1000, "amount_max": 10000,
                    "frequency": 1, "active": False, "timezone": "TH",
                    "time1": {"type": "exact", "value": "10:00"}}
    settings["text"] = text
    save_settings(user_id, settings)
    edit_mode = context.user_data.get("edit_mode", "full")
    if edit_mode == "text_only":
        await update.message.reply_text("✅ Текст сохранён!\n\nНапиши /start")
        return MENU
    await update.message.reply_text("✅ Текст сохранён!\n\n💵 Введи *минимальную* сумму (число):", parse_mode="Markdown")
    return EDIT_AMOUNT_MIN


async def receive_amount_min(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(" ", "").replace(",", "."))
        context.user_data["amount_min"] = val
        await update.message.reply_text(f"✅ Минимум: *{val:,.0f}*\n\nВведи *максимальную* сумму:", parse_mode="Markdown")
        return EDIT_AMOUNT_MAX
    except:
        await update.message.reply_text("⚠️ Введи число, например: `5000`", parse_mode="Markdown")
        return EDIT_AMOUNT_MIN


async def receive_amount_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(" ", "").replace(",", "."))
        user_id = update.effective_user.id
        settings = load_settings(user_id)
        settings["amount_min"] = context.user_data.get("amount_min", 1000)
        settings["amount_max"] = val
        save_settings(user_id, settings)
        edit_mode = context.user_data.get("edit_mode", "full")
        if edit_mode == "amount_only":
            await update.message.reply_text(f"✅ Сумма: *{settings['amount_min']:,.0f}–{val:,.0f}*\n\nНапиши /start", parse_mode="Markdown")
            return MENU
        # full setup — переходим к валюте
        await update.message.reply_text(
            f"✅ Сумма: *{settings['amount_min']:,.0f}–{val:,.0f}*\n\n💱 Выбери валюту:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇷🇺 Рубли ₽", callback_data="set_cur_RUB")],
                [InlineKeyboardButton("🇺🇸 Доллары $", callback_data="set_cur_USD")],
                [InlineKeyboardButton("🇹🇭 Тайские баты ฿", callback_data="set_cur_THB")],
            ]), parse_mode="Markdown"
        )
        return MENU
    except:
        await update.message.reply_text("⚠️ Введи число, например: `50000`", parse_mode="Markdown")
        return EDIT_AMOUNT_MAX


# ===== ВРЕМЯ 1 =====

async def receive_t1_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T1_TIME
    t1_type = context.user_data.get("t1_type", "exact")
    if t1_type == "exact":
        user_id = update.effective_user.id
        settings = load_settings(user_id)
        settings["time1"] = {"type": "exact", "value": t}
        settings["scheduled_times_today"] = []
        save_settings(user_id, settings)
        await update.message.reply_text(f"✅ Время 1: *{t}*\n\nНапиши /start", parse_mode="Markdown")
        return MENU
    else:
        context.user_data["t1_start"] = t
        await update.message.reply_text(f"✅ Начало: *{t}*\n\nВведи *конец* диапазона:", parse_mode="Markdown")
        return EDIT_T1_END


async def receive_t1_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T1_END
    user_id = update.effective_user.id
    settings = load_settings(user_id)
    start_t = context.user_data.get("t1_start", "09:00")
    settings["time1"] = {"type": "range", "start": start_t, "end": t}
    settings["scheduled_times_today"] = []
    save_settings(user_id, settings)
    await update.message.reply_text(f"✅ Время 1: *{start_t}–{t}*\n\nНапиши /start", parse_mode="Markdown")
    return MENU


# ===== ВРЕМЯ 2 =====

async def receive_t2_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T2_TIME
    t2_type = context.user_data.get("t2_type", "exact")
    if t2_type == "exact":
        user_id = update.effective_user.id
        settings = load_settings(user_id)
        settings["time2"] = {"type": "exact", "value": t}
        settings["scheduled_times_today"] = []
        save_settings(user_id, settings)
        await update.message.reply_text(f"✅ Время 2: *{t}*\n\nНапиши /start", parse_mode="Markdown")
        return MENU
    else:
        context.user_data["t2_start"] = t
        await update.message.reply_text(f"✅ Начало: *{t}*\n\nВведи *конец* диапазона:", parse_mode="Markdown")
        return EDIT_T2_END


async def receive_t2_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return EDIT_T2_END
    user_id = update.effective_user.id
    settings = load_settings(user_id)
    start_t = context.user_data.get("t2_start", "18:00")
    settings["time2"] = {"type": "range", "start": start_t, "end": t}
    settings["scheduled_times_today"] = []
    save_settings(user_id, settings)
    await update.message.reply_text(f"✅ Время 2: *{start_t}–{t}*\n\nНапиши /start", parse_mode="Markdown")
    return MENU


# ===== ПЛАНИРОВЩИК =====

async def schedule_notifications(app: Application):
    while True:
        await asyncio.sleep(30)
        try:
            if not os.path.exists(SETTINGS_FILE):
                continue
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                all_settings = json.load(f)

            for user_id_str, settings in all_settings.items():
                if not settings.get("active", False):
                    continue

                user_now = get_user_now(settings)
                today_str = user_now.strftime("%Y-%m-%d")
                current_time_str = user_now.strftime("%H:%M")
                frequency = int(settings.get("frequency", 1))

                next_send_date = settings.get("next_send_date")
                if next_send_date and today_str < next_send_date:
                    continue
                # Сбрасываем next_send_date если сегодня уже можно слать
                if next_send_date and today_str >= next_send_date:
                    settings["next_send_date"] = None

                if settings.get("sent_date") != today_str:
                    settings["sent_today"] = []
                    settings["sent_date"] = today_str

                if settings.get("scheduled_date") != today_str or not settings.get("scheduled_times_today"):
                    scheduled = []
                    for slot in ["time1", "time2"]:
                        slot_data = settings.get(slot)
                        if not slot_data:
                            continue
                        if slot_data.get("type") == "exact":
                            scheduled.append(slot_data["value"])
                        else:
                            scheduled.append(get_random_time(slot_data["start"], slot_data["end"]))
                    settings["scheduled_times_today"] = scheduled
                    settings["scheduled_date"] = today_str

                sent_today = settings.get("sent_today", [])
                for t in settings.get("scheduled_times_today", []):
                    if t <= current_time_str and t not in sent_today:
                        try:
                            await app.bot.send_message(
                                chat_id=int(user_id_str),
                                text=generate_notification(settings),
                                parse_mode="Markdown"
                            )
                            sent_today.append(t)
                            settings["sent_today"] = sent_today
                            if len(sent_today) >= len(settings.get("scheduled_times_today", [])):
                                next_d = user_now.date() + timedelta(days=frequency)
                                settings["next_send_date"] = next_d.strftime("%Y-%m-%d")
                                settings["scheduled_times_today"] = []
                            save_settings(int(user_id_str), settings)
                        except Exception as e:
                            logger.error(f"Send error {user_id_str}: {e}")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")


# ===== ЗАПУСК =====

async def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        print("❌ Установи BOT_TOKEN")
        return

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(button_handler)],
            EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            EDIT_AMOUNT_MIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount_min)],
            EDIT_AMOUNT_MAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount_max),
                CallbackQueryHandler(button_handler),
            ],
            EDIT_T1_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_t1_time)],
            EDIT_T1_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_t1_end)],
            EDIT_T2_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_t2_time)],
            EDIT_T2_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_t2_end)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)

    print("🤖 Бот запущен!")
    async with app:
        await app.start()
        asyncio.create_task(schedule_notifications(app))
        await app.updater.start_polling(drop_pending_updates=True)
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
