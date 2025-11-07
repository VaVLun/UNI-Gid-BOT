import os
import logging
import random
import sqlite3
import asyncio
import threading
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask

# ТОКЕН БОТА - ЗАМЕНИ ЭТУ СТРОКУ!
BOT_TOKEN = "8336386577:AAF1kKtD1akVWzvtK_cZIeEdPw4tpORHibc"

# Настройка логов
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "UNI Gid Bot is running!"

# Глобальный словарь для хранения активных таймеров
active_timers = {}


# База данных
def init_db():
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            class_id TEXT PRIMARY KEY,
            class_name TEXT,
            schedule TEXT,
            admin_id INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            class_id TEXT,
            subject TEXT,
            url TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            class_id TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            notifications_enabled BOOLEAN DEFAULT 1,
            reminder_minutes INTEGER DEFAULT 5
        )
    ''')

    conn.commit()
    conn.close()


init_db()


# Функции для работы с базой данных
def save_class(class_id, class_name, admin_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO classes (class_id, class_name, admin_id) VALUES (?, ?, ?)",
                   (class_id, class_name, admin_id))
    conn.commit()
    conn.close()


def save_schedule(class_id, schedule):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE classes SET schedule = ? WHERE class_id = ?", (schedule, class_id))
    conn.commit()
    conn.close()


def save_links(class_id, links_text):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM links WHERE class_id = ?", (class_id,))

    for line in links_text.split('\n'):
        if ':' in line and 'http' in line:
            try:
                subject, url = line.split(':', 1)
                subject = subject.strip()
                url = url.strip()
                cursor.execute("INSERT INTO links (class_id, subject, url) VALUES (?, ?, ?)",
                               (class_id, subject, url))
            except:
                continue

    conn.commit()
    conn.close()


def join_user_to_class(user_id, class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    if class_id is None:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, class_id) VALUES (?, ?)", (user_id, class_id))
    conn.commit()
    conn.close()


def get_user_settings(user_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT notifications_enabled, reminder_minutes FROM user_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {'notifications_enabled': bool(result[0]), 'reminder_minutes': result[1]}
    else:
        default_settings = {'notifications_enabled': True, 'reminder_minutes': 5}
        save_user_settings(user_id, default_settings)
        return default_settings


def save_user_settings(user_id, settings):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO user_settings (user_id, notifications_enabled, reminder_minutes) VALUES (?, ?, ?)",
        (user_id, settings['notifications_enabled'], settings['reminder_minutes']))
    conn.commit()
    conn.close()


def get_class_info(class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT class_name, schedule, admin_id FROM classes WHERE class_id = ?", (class_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_class_links(class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT subject, url FROM links WHERE class_id = ?", (class_id,))
    links = cursor.fetchall()
    conn.close()
    return links


def class_exists(class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM classes WHERE class_id = ?", (class_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_user_class(user_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT class_id FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def is_user_admin_of_class(user_id, class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM classes WHERE class_id = ? AND admin_id = ?", (class_id, user_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_all_classes():
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT class_id, class_name, admin_id FROM classes")
    results = cursor.fetchall()
    conn.close()
    return results


def get_class_users(class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE class_id = ?", (class_id,))
    results = cursor.fetchall()
    conn.close()
    return [user[0] for user in results]


def get_all_users():
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, class_id FROM users")
    results = cursor.fetchall()
    conn.close()
    return results


# Функции для удаления данных
def delete_all_users():
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    print("✅ Все ученики удалены из базы данных")


def delete_all_classes():
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM classes")
    cursor.execute("DELETE FROM links")
    cursor.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    print("✅ Все классы удалены из базы данных")


def delete_class(class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM classes WHERE class_id = ?", (class_id,))
    cursor.execute("DELETE FROM links WHERE class_id = ?", (class_id,))
    cursor.execute("DELETE FROM users WHERE class_id = ?", (class_id,))
    conn.commit()
    conn.close()
    print(f"✅ Класс {class_id} удален")


def delete_user_from_class(user_id, class_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ? AND class_id = ?", (user_id, class_id))
    conn.commit()
    conn.close()
    print(f"✅ Пользователь {user_id} удален из класса {class_id}")


def delete_user(user_id):
    conn = sqlite3.connect('uni_gid.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"✅ Пользователь {user_id} удален")


# Парсинг расписания и таймеры
def parse_schedule(schedule_text):
    """Парсит расписание и возвращает список уроков"""
    lessons = []
    current_day = None
    lines = schedule_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Проверяем день недели
        day_keywords = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
        if any(day in line.lower() for day in day_keywords):
            current_day = line
            continue

        # Парсим урок (формат: "1. Математика 9:00-9:45")
        if current_day and '.' in line and any(char.isdigit() for char in line):
            try:
                parts = line.split('.', 1)
                if len(parts) == 2:
                    lesson_info = parts[1].strip()
                    # Ищем время
                    time_match = None
                    for word in lesson_info.split():
                        if '-' in word and ':' in word:
                            time_match = word
                            break

                    if time_match:
                        # Извлекаем название предмета
                        subject = lesson_info.split(time_match)[0].strip()
                        start_time_str = time_match.split('-')[0].strip()

                        try:
                            start_time = datetime.strptime(start_time_str, '%H:%M').time()
                            lessons.append({
                                'day': current_day,
                                'subject': subject,
                                'start_time': start_time,
                                'time_str': time_match
                            })
                        except:
                            continue
            except:
                continue

    return lessons


def get_todays_lessons(schedule_text):
    """Получает уроки на сегодня"""
    lessons = parse_schedule(schedule_text)
    if not lessons:
        return []

    now = datetime.now()
    current_weekday = now.strftime('%A').lower()

    # Маппинг русских дней на английские
    day_mapping = {
        'понедельник': 'monday',
        'вторник': 'tuesday',
        'среда': 'wednesday',
        'четверг': 'thursday',
        'пятница': 'friday',
        'суббота': 'saturday',
        'воскресенье': 'sunday'
    }

    today_lessons = []
    for lesson in lessons:
        russian_day = lesson['day'].split(':')[0].strip().lower()
        english_day = day_mapping.get(russian_day)
        if english_day == current_weekday:
            today_lessons.append(lesson)

    # Сортируем уроки по времени
    today_lessons.sort(key=lambda x: x['start_time'])
    return today_lessons


async def start_reminder_timer(user_id, class_id, application):
    """Запускает таймеры напоминаний для пользователя"""
    try:
        # Останавливаем старые таймеры для этого пользователя
        if user_id in active_timers:
            for timer in active_timers[user_id]:
                timer.cancel()
            active_timers[user_id] = []

        settings = get_user_settings(user_id)
        if not settings['notifications_enabled']:
            return

        class_info = get_class_info(class_id)
        if not class_info or not class_info[1]:
            return

        schedule_text = class_info[1]
        today_lessons = get_todays_lessons(schedule_text)

        if not today_lessons:
            return

        current_time = datetime.now()
        today_date = current_time.date()

        active_timers[user_id] = []

        for lesson in today_lessons:
            # Создаем datetime объект для начала урока
            lesson_datetime = datetime.combine(today_date, lesson['start_time'])

            # Если урок уже прошел, пропускаем
            if lesson_datetime <= current_time:
                continue

            # Время напоминания (за N минут до урока)
            reminder_time = lesson_datetime - timedelta(minutes=settings['reminder_minutes'])

            # Если время напоминания уже прошло, но урок еще не начался, напоминаем сразу
            if reminder_time <= current_time:
                # Урок скоро начнется, напоминаем сразу
                await send_reminder(user_id, lesson, class_id, application)
            else:
                # Запускаем таймер
                delay = (reminder_time - current_time).total_seconds()
                timer = asyncio.get_event_loop().call_later(
                    delay,
                    lambda: asyncio.create_task(send_reminder(user_id, lesson, class_id, application))
                )
                active_timers[user_id].append(timer)

                logger.info(
                    f"⏰ Таймер установлен для пользователя {user_id} на урок {lesson['subject']} через {delay:.0f} сек")

    except Exception as e:
        logger.error(f"❌ Ошибка запуска таймера для пользователя {user_id}: {e}")


async def send_reminder(user_id, lesson, class_id, application):
    """Отправляет напоминание об уроке"""
    try:
        links = get_class_links(class_id)
        lesson_link = None
        for subject, url in links:
            if lesson['subject'].lower() in subject.lower():
                lesson_link = url
                break

        message = f"🔔 НАПОМИНАНИЕ ОБ УРОКЕ!\n\n"
        message += f"📚 {lesson['subject']}\n"
        message += f"📅 {lesson['day']}\n"
        message += f"🕐 Начинается в {lesson['time_str']}\n"

        if lesson_link:
            message += f"🔗 Ссылка: {lesson_link}"

        await application.bot.send_message(chat_id=user_id, text=message)
        logger.info(f"📨 Отправлено напоминание пользователю {user_id} об уроке {lesson['subject']}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки напоминания пользователю {user_id}: {e}")


# Консольные команды
def console_commands(application):
    """Обработчик консольных команд"""
    while True:
        try:
            command = input("\n>>> ").strip().lower()

            if command == 'help':
                print("""
🔧 КОНСОЛЬНЫЕ КОМАНДЫ:

🗑️ Удаление данных:
delete_all_users - удалить всех учеников
delete_all_classes - удалить все классы
delete_class CLASS_ID - удалить конкретный класс
delete_user USER_ID - удалить пользователя полностью
remove_from_class USER_ID CLASS_ID - удалить ученика из класса

📊 Просмотр данных:
show_classes - показать все классы
show_users - показать всех пользователей
show_timers - показать активные таймеры

🎯 Тестирование:
create_test_class - создать тестовый класс
start_timers - запустить все таймеры
stop_timers USER_ID - остановить таймеры пользователя
exit - выйти из бота

Примеры:
delete_class 10А_1234
delete_user 123456789
remove_from_class 123456789 10А_1234
start_timers
""")

            elif command == 'delete_all_users':
                delete_all_users()

            elif command == 'delete_all_classes':
                delete_all_classes()

            elif command.startswith('delete_class '):
                class_id = command.replace('delete_class ', '').strip()
                if class_exists(class_id):
                    delete_class(class_id)
                else:
                    print("❌ Класс не найден")

            elif command.startswith('delete_user '):
                try:
                    user_id = int(command.replace('delete_user ', '').strip())
                    delete_user(user_id)
                except ValueError:
                    print("❌ Неверный формат user_id")

            elif command.startswith('remove_from_class '):
                try:
                    parts = command.replace('remove_from_class ', '').strip().split()
                    if len(parts) == 2:
                        user_id = int(parts[0])
                        class_id = parts[1]
                        delete_user_from_class(user_id, class_id)
                    else:
                        print("❌ Формат: remove_from_class user_id class_id")
                except ValueError:
                    print("❌ Неверный формат user_id")

            elif command == 'show_classes':
                classes = get_all_classes()
                if classes:
                    print("\n📚 ВСЕ КЛАССЫ:")
                    for class_id, class_name, admin_id in classes:
                        users = get_class_users(class_id)
                        print(f"🏫 {class_name} (ID: {class_id})")
                        print(f"👨‍🏫 Админ: {admin_id}")
                        print(f"👥 Учеников: {len(users)}")
                        print()
                else:
                    print("❌ Нет созданных классов")

            elif command == 'show_users':
                users = get_all_users()
                if users:
                    print("\n👥 ВСЕ ПОЛЬЗОВАТЕЛИ:")
                    for user_id, class_id in users:
                        class_info = get_class_info(class_id) if class_id else None
                        class_name = class_info[0] if class_info else "не в классе"
                        print(f"👤 {user_id} - Класс: {class_name}")
                else:
                    print("❌ Нет пользователей в базе")

            elif command == 'show_timers':
                if active_timers:
                    print("\n⏰ АКТИВНЫЕ ТАЙМЕРЫ:")
                    for user_id, timers in active_timers.items():
                        print(f"👤 Пользователь {user_id}: {len(timers)} таймеров")
                else:
                    print("❌ Нет активных таймеров")

            elif command == 'create_test_class':
                class_name = "10А"
                class_id = f"{class_name}_{random.randint(1000, 9999)}"
                admin_id = 123456789

                save_class(class_id, class_name, admin_id)

                schedule = """Понедельник:
1. Математика 9:00-9:45
2. Физика 10:00-10:45

Вторник:
1. История 9:00-9:45
2. Химия 10:00-10:45"""

                save_schedule(class_id, schedule)

                links = """Математика: https://zoom.us/j/123456789
Физика: https://meet.google.com/abc-def-ghi
История: https://discord.gg/example
Химия: https://meet.google.com/xyz-uvw-rst"""

                save_links(class_id, links)

                print(f"✅ Тестовый класс создан: {class_name} (ID: {class_id})")

            elif command == 'start_timers':
                print("🔄 Запуск всех таймеров...")
                users = get_all_users()
                for user_id, class_id in users:
                    asyncio.create_task(start_reminder_timer(user_id, class_id, application))
                print("✅ Все таймеры запущены")

            elif command.startswith('stop_timers '):
                try:
                    user_id = int(command.replace('stop_timers ', '').strip())
                    if user_id in active_timers:
                        for timer in active_timers[user_id]:
                            timer.cancel()
                        active_timers[user_id] = []
                        print(f"✅ Таймеры пользователя {user_id} остановлены")
                    else:
                        print("❌ У пользователя нет активных таймеров")
                except ValueError:
                    print("❌ Неверный формат user_id")

            elif command == 'exit':
                print("👋 Выход из бота...")
                break

            else:
                print("❌ Неизвестная команда. Напиши 'help' для списка команд")

        except KeyboardInterrupt:
            print("\n👋 Выход из бота...")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")


# Главное меню и функции бота
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        user_class = get_user_class(user_id)

        if user_class:
            class_info = get_class_info(user_class)
            class_name = class_info[0] if class_info else "класс"

            is_admin = is_user_admin_of_class(user_id, user_class)

            if is_admin:
                keyboard = [
                    ["📅 Расписание", "🔗 Ссылки"],
                    ["⏰ Ближайший урок", "🔔 Настройки уведомлений"],
                    ["📤 Поделиться классом", "🚪 Выйти из класса"]
                ]
            else:
                keyboard = [
                    ["📅 Расписание", "🔗 Ссылки"],
                    ["⏰ Ближайший урок", "🔔 Настройки уведомлений"],
                    ["🚪 Выйти из класса"]
                ]

            text = f"🎓 UNI Gid\n🏫 Класс: {class_name}"
        else:
            keyboard = [
                ["🏫 Создать класс", "🔗 Присоединиться"]
            ]
            text = "🎓 UNI Gid - Ваш учебный помощник"

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка отправки меню: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id

        if context.args:
            class_id = context.args[0]
            if class_exists(class_id):
                class_info = get_class_info(class_id)
                class_name = class_info[0] if class_info else "класс"

                keyboard = [
                    ["✅ Да, присоединиться", "❌ Нет, остаться"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

                await update.message.reply_text(
                    f"🔗 Вас пригласили в класс: {class_name}\n\nПрисоединиться к этому классу?",
                    reply_markup=reply_markup
                )
                context.user_data['pending_class_id'] = class_id
                return
            else:
                await update.message.reply_text("❌ Класс не найден")
                await show_main_menu(update, context)
                return

        await show_main_menu(update, context)

    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text

        # Обработка подтверждения присоединения к классу
        if context.user_data.get('pending_class_id'):
            if text == "✅ Да, присоединиться":
                class_id = context.user_data['pending_class_id']
                join_user_to_class(user_id, class_id)
                class_info = get_class_info(class_id)
                class_name = class_info[0] if class_info else "класс"
                await update.message.reply_text(f"✅ Вы присоединились к классу '{class_name}'!")

                # Запускаем таймеры для нового пользователя
                await start_reminder_timer(user_id, class_id, context.application)

                context.user_data.pop('pending_class_id', None)
                await show_main_menu(update, context)
                return
            elif text == "❌ Нет, остаться":
                await update.message.reply_text("❌ Вы отказались от присоединения.")
                context.user_data.pop('pending_class_id', None)
                await show_main_menu(update, context)
                return

        # Основное меню
        if text == "🏠 Главное меню":
            await show_main_menu(update, context)
            return

        elif text == "📅 Расписание":
            user_class = get_user_class(user_id)
            if user_class:
                class_info = get_class_info(user_class)
                schedule = class_info[1] if class_info and class_info[1] else "Расписание не добавлено"
                await update.message.reply_text(f"📅 РАСПИСАНИЕ:\n\n{schedule}")
            else:
                await update.message.reply_text("❌ Вы не подключены к классу")
            return

        elif text == "🔗 Ссылки":
            user_class = get_user_class(user_id)
            if user_class:
                links = get_class_links(user_class)
                if links:
                    links_text = "🔗 ССЫЛКИ:\n\n"
                    for subject, url in links:
                        links_text += f"• {subject}: {url}\n"
                    await update.message.reply_text(links_text)
                else:
                    await update.message.reply_text("❌ Ссылки не добавлены")
            else:
                await update.message.reply_text("❌ Вы не подключены к классу")
            return

        elif text == "⏰ Ближайший урок":
            user_class = get_user_class(user_id)
            if user_class:
                class_info = get_class_info(user_class)
                schedule_text = class_info[1] if class_info and class_info[1] else None

                if schedule_text:
                    today_lessons = get_todays_lessons(schedule_text)
                    current_time = datetime.now().time()

                    next_lesson = None
                    for lesson in today_lessons:
                        if lesson['start_time'] > current_time:
                            next_lesson = lesson
                            break

                    if next_lesson:
                        time_until = datetime.combine(datetime.now().date(), next_lesson['start_time']) - datetime.now()
                        minutes_until = int(time_until.total_seconds() / 60)

                        message = f"⏰ БЛИЖАЙШИЙ УРОК:\n\n"
                        message += f"📚 {next_lesson['subject']}\n"
                        message += f"📅 {next_lesson['day']}\n"
                        message += f"🕐 Через {minutes_until} минут ({next_lesson['time_str']})"

                        await update.message.reply_text(message)
                    else:
                        await update.message.reply_text("ℹ️ На сегодня уроков больше нет")
                else:
                    await update.message.reply_text("❌ Расписание не добавлено")
            else:
                await update.message.reply_text("❌ Вы не подключены к классу")
            return

        elif text == "🔔 Настройки уведомлений":
            settings = get_user_settings(user_id)
            status = "🔔 ВКЛЮЧЕНЫ" if settings['notifications_enabled'] else "🔕 ВЫКЛЮЧЕНЫ"

            keyboard = [
                ["🔔 Включить уведомления", "🔕 Выключить уведомления"],
                ["5 минут", "10 минут", "15 минут"],
                ["🏠 Главное меню"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            message = f"🔔 НАСТРОЙКИ УВЕДОМЛЕНИЙ\n\n"
            message += f"Статус: {status}\n"
            message += f"Напоминание за: {settings['reminder_minutes']} минут\n\n"
            message += "Выберите действие:"

            await update.message.reply_text(message, reply_markup=reply_markup)
            context.user_data['setting_notifications'] = True
            return

        elif text == "📤 Поделиться классом":
            user_class = get_user_class(user_id)
            if user_class and is_user_admin_of_class(user_id, user_class):
                bot_username = (await context.bot.get_me()).username
                invite_link = f"https://t.me/{bot_username}?start={user_class}"

                class_info = get_class_info(user_class)
                class_name = class_info[0] if class_info else "класс"

                await update.message.reply_text(
                    f"📤 ПОДЕЛИТЬСЯ КЛАССОМ\n\n"
                    f"Класс: {class_name}\n\n"
                    f"Ссылка для приглашения:\n`{invite_link}`\n\n"
                    f"Отправьте эту ссылку ученикам!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ У вас нет прав для управления этим классом")
            return

        elif text == "🚪 Выйти из класса":
            user_class = get_user_class(user_id)
            if user_class:
                class_info = get_class_info(user_class)
                class_name = class_info[0] if class_info else "класс"

                # Останавливаем таймеры
                if user_id in active_timers:
                    for timer in active_timers[user_id]:
                        timer.cancel()
                    active_timers[user_id] = []

                join_user_to_class(user_id, None)
                await update.message.reply_text(f"✅ Вы вышли из класса '{class_name}'")
                await show_main_menu(update, context)
            else:
                await update.message.reply_text("❌ Вы не состоите в классе")
            return

        elif text == "🏫 Создать класс":
            await update.message.reply_text("🏫 Введите название класса:\n(например: 10А, 9Б)")
            context.user_data['step'] = 'class_name'
            return

        elif text == "🔗 Присоединиться":
            await update.message.reply_text("🔗 Введите ID класса для подключения:")
            context.user_data['step'] = 'join_class_id'
            return

        # Обработка настроек уведомлений
        if context.user_data.get('setting_notifications'):
            if text == "🔔 Включить уведомления":
                settings = get_user_settings(user_id)
                settings['notifications_enabled'] = True
                save_user_settings(user_id, settings)

                # Перезапускаем таймеры
                user_class = get_user_class(user_id)
                if user_class:
                    await start_reminder_timer(user_id, user_class, context.application)

                await update.message.reply_text("✅ Уведомления включены! Бот будет присылать напоминания об уроках.")
                context.user_data.pop('setting_notifications', None)
                await show_main_menu(update, context)
                return

            elif text == "🔕 Выключить уведомления":
                settings = get_user_settings(user_id)
                settings['notifications_enabled'] = False
                save_user_settings(user_id, settings)

                # Останавливаем таймеры
                if user_id in active_timers:
                    for timer in active_timers[user_id]:
                        timer.cancel()
                    active_timers[user_id] = []

                await update.message.reply_text("✅ Уведомления выключены.")
                context.user_data.pop('setting_notifications', None)
                await show_main_menu(update, context)
                return

            elif text in ["5 минут", "10 минут", "15 минут"]:
                minutes = int(text.split()[0])
                settings = get_user_settings(user_id)
                settings['reminder_minutes'] = minutes
                save_user_settings(user_id, settings)

                # Перезапускаем таймеры
                user_class = get_user_class(user_id)
                if user_class:
                    await start_reminder_timer(user_id, user_class, context.application)

                await update.message.reply_text(f"✅ Напоминание установлено за {minutes} минут до урока!")
                context.user_data.pop('setting_notifications', None)
                await show_main_menu(update, context)
                return

        # Обработка шагов создания класса
        if context.user_data.get('step') == 'class_name':
            class_name = text.strip()
            class_id = f"{class_name}_{random.randint(1000, 9999)}"

            save_class(class_id, class_name, user_id)
            join_user_to_class(user_id, class_id)

            context.user_data['class_id'] = class_id
            context.user_data['class_name'] = class_name
            context.user_data['step'] = 'schedule'

            await update.message.reply_text(
                f"✅ Класс '{class_name}' создан!\n\n📅 Отправьте расписание уроков:\n\nПример:\nПонедельник:\n1. Математика 9:00-9:45\n2. Физика 10:00-10:45"
            )

        elif context.user_data.get('step') == 'schedule':
            schedule = text
            class_id = context.user_data['class_id']

            save_schedule(class_id, schedule)
            context.user_data['step'] = 'links'

            await update.message.reply_text(
                "📝 Расписание сохранено!\n\n🔗 Теперь отправьте ссылки на уроки:\n\nФормат:\nМатематика: https://zoom.us/j/123\nФизика: https://meet.google.com/abc"
            )

        elif context.user_data.get('step') == 'links':
            links = text
            class_id = context.user_data['class_id']
            class_name = context.user_data['class_name']

            save_links(class_id, links)

            bot_username = (await context.bot.get_me()).username
            invite_link = f"https://t.me/{bot_username}?start={class_id}"

            await update.message.reply_text(
                f"🎉 Класс '{class_name}' готов!\n\n🔗 Ссылка для приглашения:\n`{invite_link}`\n\nОтправьте эту ссылку ученикам!",
                parse_mode='Markdown'
            )

            # Запускаем таймеры для создателя класса
            await start_reminder_timer(user_id, class_id, context.application)

            context.user_data.clear()
            await asyncio.sleep(1)
            await show_main_menu(update, context)

        elif context.user_data.get('step') == 'join_class_id':
            class_id = text.strip()
            if class_exists(class_id):
                class_info = get_class_info(class_id)
                class_name = class_info[0] if class_info else "класс"

                keyboard = [
                    ["✅ Да, присоединиться", "❌ Нет, отмена"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

                await update.message.reply_text(
                    f"🔗 Присоединиться к классу: {class_name}?",
                    reply_markup=reply_markup
                )
                context.user_data['pending_join_class_id'] = class_id
                context.user_data['step'] = None
            else:
                await update.message.reply_text("❌ Класс не найден. Попробуйте еще раз:")

        # Обработка подтверждения присоединения по ID
        if context.user_data.get('pending_join_class_id'):
            if text == "✅ Да, присоединиться":
                class_id = context.user_data['pending_join_class_id']
                join_user_to_class(user_id, class_id)
                class_info = get_class_info(class_id)
                class_name = class_info[0] if class_info else "класс"
                await update.message.reply_text(f"✅ Вы присоединились к классу '{class_name}'!")

                # Запускаем таймеры для нового пользователя
                await start_reminder_timer(user_id, class_id, context.application)

                context.user_data.pop('pending_join_class_id', None)
                await show_main_menu(update, context)
                return
            elif text == "❌ Нет, отмена":
                await update.message.reply_text("❌ Присоединение отменено.")
                context.user_data.pop('pending_join_class_id', None)
                await show_main_menu(update, context)
                return

    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")


def run_bot():
    """Функция запуска бота для Render"""
    # Используем глобальный токен
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден")
        return

    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    print("🎓 UNI Gid Bot запускается...")
    print("📚 Бот для управления учебными классами и напоминаний об уроках")
    print("⚙️ Для просмотра консольных команд введите 'help'")

    # Запуск консольных команд в отдельном потоке
    console_thread = threading.Thread(target=console_commands, args=(application,), daemon=True)
    console_thread.start()

    # Запуск бота
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")


def main():
    """Основная функция запуска для Render"""
    # Запуск Flask сервера в отдельном потоке
    port = int(os.environ.get('PORT', 5000))
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    # Запуск бота
    run_bot()


if __name__ == '__main__':
    main()
