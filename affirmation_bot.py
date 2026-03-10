#!/usr/bin/env python3
"""
💰 Бот-аффирмации денежных поступлений
Имитирует уведомления о поступлении денежных средств
"""

import asyncio
import random
import json
import os
import logging
from datetime import datetime, time as dtime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Состояния диалога ---
(
    MENU, SET_TEXT, SET_AMOUNT_MIN, SET_AMOUNT_MAX,
    SET_CURRENCY, SET_FREQUENCY, SET_TIME1_TYPE, SET_TIME1,
    SET_TIME1_END, SET_TIME2_TYPE, SET_TIME2, SET_TIME2_END
) = range(12)

# --- Хранилище настроек (файл) ---
SETTINGS_FILE = "bot_settings.json"

CURRENCIES = {
    "RUB": "₽",
    "USD": "$",
    "THB": "฿"
}

FREQUENCY_OPTIONS = {
    "1": "каждый день",
    "2": "раз в 2 дня",
    "3": "раз в 3 дня",
    "4": "раз в 4 дня",
    "5": "раз в 5 дней",
    "6": "раз в 6 дней",
}


def load_settings(user_id: int) -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(str(user_id), {})
    return {}


def save_settings(user_id: int, settings: dict):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[str(user_id)] = settings
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_amount(amount: float, currency: str) -> str:
    sym = CURRENCIES.get(currency, currency)
    if currency == "RUB":
        return f"{amount:,.0f} {sym}".replace(",", " ")
    elif currency == "USD":
        return f"{sym}{amount:,.2f}"
    elif currency == "THB":
        return f"{amount:,.0f} {sym}".replace(",", " ")
    return f"{amount} {sym}"


def generate_notification(settings: dict) -> str:
    amount_min = settings.get("amount_min", 1000)
    amount_max = settings.get("amount_max", 10000)
    currency = settings.get("currency", "RUB")
    text = settings.get("text", "Поступление средств")

    amount = random.uniform(float(amount_min), float(amount_max))
    # Округляем красиво
    if currency == "RUB":
        amount = round(amount / 100) * 100
    elif currency == "USD":
        amount = round(amount, 2)
    elif currency == "THB":
        amount = round(amount / 50) * 50

    formatted = format_amount(amount, currency)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    return (
        f"💰 *Поступление средств*\n\n"
        f"📋 {text}\n"
        f"💵 Сумма: *{formatted}*\n"
        f"🕐 {now}\n\n"
        f"✅ Средства зачислены на ваш счёт"
    )


def get_random_time_in_range(time_start: str, time_end: str) -> dtime:
    """Возвращает случайное время в диапазоне HH:MM - HH:MM"""
    h1, m1 = map(int, time_start.split(":"))
    h2, m2 = map(int, time_end.split(":"))
    total_min_1 = h1 * 60 + m1
    total_min_2 = h2 * 60 + m2
    chosen = random.randint(total_min_1, total_min_2)
    return dtime(chosen // 60, chosen % 60)


# ---- Планировщик уведомлений ----
async def schedule_notifications(app: Application):
    """Фоновая задача: проверяет и отправляет уведомления"""
    while True:
        await asyncio.sleep(30)  # проверяем каждые 30 секунд
        try:
            if not os.path.exists(SETTINGS_FILE):
                continue
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                all_settings = json.load(f)

            now = datetime.now()

            for user_id_str, settings in all_settings.items():
                if not settings.get("active", False):
                    continue

                frequency = int(settings.get("frequency", 1))
                last_sent_date = settings.get("last_sent_date")
                next_send_date = settings.get("next_send_date")

                # Определяем, нужно ли сегодня отправлять
                today_str = now.strftime("%Y-%m-%d")

                if next_send_date and today_str < next_send_date:
                    continue

                # Проверяем временные окна
                sent_today = settings.get("sent_today", [])
                if today_str != settings.get("sent_date", ""):
                    sent_today = []
                    settings["sent_date"] = today_str
                    settings["sent_today"] = []

                # Определяем запланированные времена на сегодня
                if "scheduled_times_today" not in settings or settings.get("scheduled_date") != today_str:
                    scheduled = []
                    for slot in ["time1", "time2"]:
                        slot_data = settings.get(slot)
                        if not slot_data:
                            continue
                        if slot_data.get("type") == "exact":
                            scheduled.append(slot_data["value"])
                        else:
                            t = get_random_time_in_range(slot_data["start"], slot_data["end"])
                            scheduled.append(f"{t.hour:02d}:{t.minute:02d}")
                    settings["scheduled_times_today"] = scheduled
                    settings["scheduled_date"] = today_str
                    save_settings(int(user_id_str), settings)

                current_time_str = now.strftime("%H:%M")
                for t in settings.get("scheduled_times_today", []):
                    if t <= current_time_str and t not in sent_today:
                        # Отправляем уведомление
                        msg = generate_notification(settings)
                        try:
                            await app.bot.send_message(
                                chat_id=int(user_id_str),
                                text=msg,
                                parse_mode="Markdown"
                            )
                            sent_today.append(t)
                            settings["sent_today"] = sent_today
                            settings["last_sent_date"] = today_str

                            # Если все времена отправлены, ставим следующую дату
                            if len(sent_today) >= len(settings.get("scheduled_times_today", [])):
                                from datetime import date, timedelta
                                next_d = date.today() + timedelta(days=frequency)
                                settings["next_send_date"] = next_d.strftime("%Y-%m-%d")
                                settings["scheduled_times_today"] = []

                            save_settings(int(user_id_str), settings)
                            logger.info(f"Sent notification to {user_id_str}")
                        except Exception as e:
                            logger.error(f"Failed to send to {user_id_str}: {e}")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")


# ---- Handlers ----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = load_settings(user_id)

    active = settings.get("active", False)
    status = "🟢 Активен" if active else "🔴 Остановлен"

    keyboard = [
        [InlineKeyboardButton("⚙️ Настроить бота", callback_data="setup")],
        [InlineKeyboardButton("▶️ Запустить" if not active else "⏹ Остановить",
                              callback_data="toggle")],
        [InlineKeyboardButton("📊 Текущие настройки", callback_data="show_settings")],
        [InlineKeyboardButton("🔔 Тестовое уведомление", callback_data="test_notify")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"💰 *Бот денежных аффирмаций*\n\n"
        f"Статус: {status}\n\n"
        f"Я буду отправлять тебе уведомления о поступлении денег — "
        f"чтобы ты видел и чувствовал их реальность! 🌟",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return MENU


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "toggle":
        settings = load_settings(user_id)
        settings["active"] = not settings.get("active", False)
        save_settings(user_id, settings)
        status = "🟢 Запущен!" if settings["active"] else "🔴 Остановлен"
        await query.edit_message_text(f"Статус изменён: {status}\n\nНапиши /start чтобы вернуться в меню.")
        return MENU

    elif data == "test_notify":
        settings = load_settings(user_id)
        if not settings:
            await query.edit_message_text("⚠️ Сначала настрой бота через ⚙️ Настроить бота\n\n/start")
            return MENU
        msg = generate_notification(settings)
        await query.message.reply_text(msg, parse_mode="Markdown")
        await query.edit_message_text("✅ Тестовое уведомление отправлено!\n\n/start")
        return MENU

    elif data == "show_settings":
        settings = load_settings(user_id)
        if not settings:
            await query.edit_message_text("⚠️ Настройки не заданы.\n\n/start")
            return MENU

        t1 = settings.get("time1", {})
        t2 = settings.get("time2", {})
        t1_str = t1.get("value") if t1.get("type") == "exact" else f"{t1.get('start')}–{t1.get('end')}"
        t2_str = t2.get("value") if t2.get("type") == "exact" else f"{t2.get('start')}–{t2.get('end')}"

        freq = FREQUENCY_OPTIONS.get(str(settings.get("frequency", 1)), "каждый день")
        currency = settings.get("currency", "RUB")
        sym = CURRENCIES.get(currency, currency)

        text = (
            f"📊 *Текущие настройки:*\n\n"
            f"📝 Текст: {settings.get('text', '—')}\n"
            f"💵 Сумма: {settings.get('amount_min')}–{settings.get('amount_max')} {sym}\n"
            f"💱 Валюта: {currency}\n"
            f"📅 Периодичность: {freq}\n"
            f"⏰ Время 1: {t1_str or '—'}\n"
            f"⏰ Время 2: {t2_str or '—'}\n"
            f"🔔 Статус: {'🟢 Активен' if settings.get('active') else '🔴 Остановлен'}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")
        await query.message.reply_text("Напиши /start чтобы вернуться в меню.")
        return MENU

    elif data == "setup":
        await query.edit_message_text(
            "📝 *Шаг 1/8: Текст уведомления*\n\n"
            "Введи текст, который будет отображаться в уведомлении.\n"
            "Например: _Перевод от клиента_ или _Доход от бизнеса_",
            parse_mode="Markdown"
        )
        return SET_TEXT

    # Выбор валюты
    elif data.startswith("currency_"):
        currency = data.split("_")[1]
        context.user_data["currency"] = currency
        await query.edit_message_text(
            f"✅ Валюта: *{currency}* {CURRENCIES[currency]}\n\n"
            f"📅 *Шаг 4/8: Периодичность*\n\nКак часто отправлять уведомления?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Каждый день", callback_data="freq_1")],
                [InlineKeyboardButton("Раз в 2 дня", callback_data="freq_2"),
                 InlineKeyboardButton("Раз в 3 дня", callback_data="freq_3")],
                [InlineKeyboardButton("Раз в 4 дня", callback_data="freq_4"),
                 InlineKeyboardButton("Раз в 5 дней", callback_data="freq_5")],
                [InlineKeyboardButton("Раз в 6 дней", callback_data="freq_6")],
            ]),
            parse_mode="Markdown"
        )
        return SET_FREQUENCY

    elif data.startswith("freq_"):
        freq = data.split("_")[1]
        context.user_data["frequency"] = freq
        await query.edit_message_text(
            f"✅ Периодичность: *{FREQUENCY_OPTIONS[freq]}*\n\n"
            f"⏰ *Шаг 5/8: Время уведомления 1*\n\n"
            f"Выбери тип времени:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Точное время", callback_data="t1_exact")],
                [InlineKeyboardButton("🎲 Случайное в диапазоне", callback_data="t1_range")],
            ]),
            parse_mode="Markdown"
        )
        return SET_TIME1_TYPE

    elif data == "t1_exact":
        context.user_data["t1_type"] = "exact"
        await query.edit_message_text(
            "⏰ Введи точное время для уведомления 1\nФормат: `ЧЧ:ММ` (например `09:30`)",
            parse_mode="Markdown"
        )
        return SET_TIME1

    elif data == "t1_range":
        context.user_data["t1_type"] = "range"
        await query.edit_message_text(
            "⏰ Введи *начало* диапазона для времени 1\nФормат: `ЧЧ:ММ` (например `09:00`)",
            parse_mode="Markdown"
        )
        return SET_TIME1

    elif data == "t2_exact":
        context.user_data["t2_type"] = "exact"
        await query.edit_message_text(
            "⏰ Введи точное время для уведомления 2\nФормат: `ЧЧ:ММ` (например `18:00`)",
            parse_mode="Markdown"
        )
        return SET_TIME2

    elif data == "t2_range":
        context.user_data["t2_type"] = "range"
        await query.edit_message_text(
            "⏰ Введи *начало* диапазона для времени 2\nФормат: `ЧЧ:ММ` (например `17:00`)",
            parse_mode="Markdown"
        )
        return SET_TIME2

    elif data == "skip_t2":
        await _finalize_settings(query, context, user_id)
        return MENU

    return MENU


async def set_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["text"] = update.message.text
    await update.message.reply_text(
        f"✅ Текст сохранён!\n\n"
        f"💵 *Шаг 2/8: Минимальная сумма*\n\nВведи минимальную сумму (только число).\nНапример: `5000`",
        parse_mode="Markdown"
    )
    return SET_AMOUNT_MIN


async def set_amount_min(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(" ", "").replace(",", "."))
        context.user_data["amount_min"] = val
        await update.message.reply_text(
            f"✅ Минимум: *{val:,.0f}*\n\n"
            f"💵 *Шаг 3/8: Максимальная сумма*\n\nВведи максимальную сумму.",
            parse_mode="Markdown"
        )
        return SET_AMOUNT_MAX
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, например: `5000`", parse_mode="Markdown")
        return SET_AMOUNT_MIN


async def set_amount_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(" ", "").replace(",", "."))
        context.user_data["amount_max"] = val
        await update.message.reply_text(
            f"✅ Максимум: *{val:,.0f}*\n\n"
            f"💱 *Шаг 4/8: Валюта*\n\nВыбери валюту:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇷🇺 Рубли (₽)", callback_data="currency_RUB")],
                [InlineKeyboardButton("🇺🇸 Доллары ($)", callback_data="currency_USD")],
                [InlineKeyboardButton("🇹🇭 Тайские баты (฿)", callback_data="currency_THB")],
            ]),
            parse_mode="Markdown"
        )
        return SET_CURRENCY
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, например: `50000`", parse_mode="Markdown")
        return SET_AMOUNT_MAX


async def set_time1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not _valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`, например `09:30`", parse_mode="Markdown")
        return SET_TIME1

    t1_type = context.user_data.get("t1_type", "exact")
    if t1_type == "exact":
        context.user_data["t1_value"] = t
        await update.message.reply_text(
            f"✅ Время 1: *{t}*\n\n"
            f"⏰ *Шаг 6/8: Время уведомления 2*\n\nДобавить второе время?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Точное время", callback_data="t2_exact")],
                [InlineKeyboardButton("🎲 Случайное в диапазоне", callback_data="t2_range")],
                [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_t2")],
            ]),
            parse_mode="Markdown"
        )
        return SET_TIME2_TYPE
    else:
        context.user_data["t1_start"] = t
        await update.message.reply_text(
            f"✅ Начало диапазона: *{t}*\n\nТеперь введи *конец* диапазона:",
            parse_mode="Markdown"
        )
        return SET_TIME1_END


async def set_time1_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not _valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return SET_TIME1_END

    context.user_data["t1_end"] = t
    start = context.user_data.get("t1_start")
    await update.message.reply_text(
        f"✅ Диапазон 1: *{start}–{t}*\n\n"
        f"⏰ *Шаг 6/8: Время уведомления 2*\n\nДобавить второе время?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Точное время", callback_data="t2_exact")],
            [InlineKeyboardButton("🎲 Случайное в диапазоне", callback_data="t2_range")],
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_t2")],
        ]),
        parse_mode="Markdown"
    )
    return SET_TIME2_TYPE


async def set_time2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not _valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return SET_TIME2

    t2_type = context.user_data.get("t2_type", "exact")
    if t2_type == "exact":
        context.user_data["t2_value"] = t
        user_id = update.effective_user.id
        await _finalize_settings_message(update.message, context, user_id)
        return MENU
    else:
        context.user_data["t2_start"] = t
        await update.message.reply_text(
            f"✅ Начало диапазона 2: *{t}*\n\nВведи *конец* диапазона:",
            parse_mode="Markdown"
        )
        return SET_TIME2_END


async def set_time2_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not _valid_time(t):
        await update.message.reply_text("⚠️ Неверный формат. Используй `ЧЧ:ММ`", parse_mode="Markdown")
        return SET_TIME2_END

    context.user_data["t2_end"] = t
    user_id = update.effective_user.id
    await _finalize_settings_message(update.message, context, user_id)
    return MENU


def _valid_time(t: str) -> bool:
    try:
        parts = t.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except:
        return False


async def _finalize_settings(query, context, user_id):
    settings = _build_settings(context)
    save_settings(user_id, settings)
    freq = FREQUENCY_OPTIONS.get(str(settings.get("frequency", 1)))
    currency = settings.get("currency", "RUB")
    sym = CURRENCIES.get(currency)

    t1 = settings.get("time1", {})
    t1_str = t1.get("value") if t1.get("type") == "exact" else f"{t1.get('start')}–{t1.get('end')}"
    t2 = settings.get("time2")
    t2_str = ""
    if t2:
        t2_str = f"\n⏰ Время 2: *{t2.get('value') if t2.get('type') == 'exact' else t2.get('start') + '–' + t2.get('end')}*"

    await query.edit_message_text(
        f"✅ *Настройки сохранены!*\n\n"
        f"📝 Текст: {settings.get('text')}\n"
        f"💵 Сумма: {settings.get('amount_min'):,.0f}–{settings.get('amount_max'):,.0f} {sym}\n"
        f"💱 Валюта: {currency}\n"
        f"📅 Периодичность: {freq}\n"
        f"⏰ Время 1: *{t1_str}*{t2_str}\n\n"
        f"Напиши /start и нажми ▶️ Запустить!",
        parse_mode="Markdown"
    )


async def _finalize_settings_message(message, context, user_id):
    settings = _build_settings(context)
    save_settings(user_id, settings)
    freq = FREQUENCY_OPTIONS.get(str(settings.get("frequency", 1)))
    currency = settings.get("currency", "RUB")
    sym = CURRENCIES.get(currency)

    t1 = settings.get("time1", {})
    t1_str = t1.get("value") if t1.get("type") == "exact" else f"{t1.get('start')}–{t1.get('end')}"
    t2 = settings.get("time2")
    t2_str = ""
    if t2:
        t2_str = f"\n⏰ Время 2: *{t2.get('value') if t2.get('type') == 'exact' else t2.get('start') + '–' + t2.get('end')}*"

    await message.reply_text(
        f"✅ *Настройки сохранены!*\n\n"
        f"📝 Текст: {settings.get('text')}\n"
        f"💵 Сумма: {settings.get('amount_min'):,.0f}–{settings.get('amount_max'):,.0f} {sym}\n"
        f"💱 Валюта: {currency}\n"
        f"📅 Периодичность: {freq}\n"
        f"⏰ Время 1: *{t1_str}*{t2_str}\n\n"
        f"Напиши /start и нажми ▶️ Запустить!",
        parse_mode="Markdown"
    )


def _build_settings(context) -> dict:
    d = context.user_data
    t1_type = d.get("t1_type", "exact")
    t1 = {"type": t1_type}
    if t1_type == "exact":
        t1["value"] = d.get("t1_value", "09:00")
    else:
        t1["start"] = d.get("t1_start", "09:00")
        t1["end"] = d.get("t1_end", "11:00")

    t2 = None
    t2_type = d.get("t2_type")
    if t2_type:
        t2 = {"type": t2_type}
        if t2_type == "exact":
            t2["value"] = d.get("t2_value", "18:00")
        else:
            t2["start"] = d.get("t2_start", "17:00")
            t2["end"] = d.get("t2_end", "20:00")

    return {
        "text": d.get("text", "Поступление средств"),
        "amount_min": d.get("amount_min", 1000),
        "amount_max": d.get("amount_max", 10000),
        "currency": d.get("currency", "RUB"),
        "frequency": int(d.get("frequency", 1)),
        "time1": t1,
        "time2": t2,
        "active": False,
        "sent_today": [],
    }


async def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        print("❌ Ошибка: Установи переменную окружения BOT_TOKEN")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(button_handler)],
            SET_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_text)],
            SET_AMOUNT_MIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_amount_min)],
            SET_AMOUNT_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_amount_max)],
            SET_CURRENCY: [CallbackQueryHandler(button_handler)],
            SET_FREQUENCY: [CallbackQueryHandler(button_handler)],
            SET_TIME1_TYPE: [CallbackQueryHandler(button_handler)],
            SET_TIME1: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time1)],
            SET_TIME1_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time1_end)],
            SET_TIME2_TYPE: [CallbackQueryHandler(button_handler)],
            SET_TIME2: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time2)],
            SET_TIME2_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time2_end)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    print("🤖 Бот запущен!")

    async with app:
        await app.start()
        asyncio.create_task(schedule_notifications(app))
        await app.updater.start_polling(drop_pending_updates=True)
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
