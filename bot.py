import asyncio
import logging
import re
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# ================= КОНФИГУРАЦИЯ =================

TOKEN = "8401269331:AAHy4Vp3fwAArHHK4JfrS1rE6jl8vNXJBsU"
ADMIN_ID = 7680186226

CHANNEL_ID = -1003626401003
DISCUSSION_CHAT_ID = -1003604185274

FOOTER_TEXT = (
    "\n\n"
    "https://t.me/+9GTEcMHyru5kZWQ0    \n"
    "Ссылка для друзей\n\n"
    "https://t.me/+RNj3e09-hqthNmM0   \n"
    "Наш чат\n\n"
    "@SlivKhersona_bot\n"
    "Прислать пост"
)

# ================= БАЗА ДАННЫХ =================

def init_db():
    with sqlite3.connect("bot_users.db") as conn:
        # 1. Создаем таблицы, если их нет
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)")
        
        # 2. АВТО-ИСПРАВЛЕНИЕ: Проверяем, есть ли колонка username
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "username" not in columns:
            print("⚠️ База данных устарела. Добавляю колонку username...")
            try:
                conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
                conn.commit()
                print("✅ База данных успешно обновлена!")
            except Exception as e:
                print(f"Ошибка обновления БД: {e}")

def add_user_to_db(user_id: int, username: str = None):
    """Добавляет пользователя или обновляет его username"""
    clean_username = username.lower() if username else None
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", 
            (user_id, clean_username)
        )
        conn.commit()

def get_all_users():
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

def ban_user_db(user_id: int):
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute("INSERT OR IGNORE INTO banned (user_id) VALUES (?)", (user_id,))
        conn.commit()

def unban_user_db(user_id: int):
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute("DELETE FROM banned WHERE user_id = ?", (user_id,))
        conn.commit()

def is_user_banned(user_id: int) -> bool:
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute("SELECT 1 FROM banned WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

def get_id_by_username(username: str):
    """Поиск ID по юзернейму"""
    clean_username = username.lower().replace("@", "").strip()
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute("SELECT user_id FROM users WHERE username = ?", (clean_username,))
        result = cursor.fetchone()
        return result[0] if result else None

# ================= ИНИЦИАЛИЗАЦИЯ =================

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

pending_comments = {}

# ================= ЛОГИКА ОБРАБОТКИ ТЕКСТА =================

def process_text(text: str):
    if not text:
        return "", []
    phone_pattern = r"(?:\+?38\s*)?0\s*\d{2}[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
    found_numbers = re.findall(phone_pattern, text)
    clean_text = re.sub(phone_pattern, " (номер в комментариях) ", text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    return clean_text, found_numbers

# ================= ХЕНДЛЕРЫ АДМИНА (BAN / UNBAN) =================

@dp.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return

    args = command.args
    if not args:
        await message.answer("⚠️ Пиши: `/ban ID` или `/ban @username`")
        return

    target_id = None
    if args.isdigit():
        target_id = int(args)
    else:
        target_id = get_id_by_username(args)
    
    if not target_id:
        await message.answer(f"❌ Пользователь {args} не найден в базе (возможно, он не писал боту).")
        return

    ban_user_db(target_id)
    await message.answer(f"⛔ Пользователь <code>{target_id}</code> ({args}) ЗАБАНЕН.")
    
    try:
        await bot.send_message(target_id, "⛔ Вы были заблокированы администратором.")
    except:
        pass

@dp.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return

    args = command.args
    if not args:
        await message.answer("⚠️ Пиши: `/unban ID` или `/unban @username`")
        return

    target_id = None
    if args.isdigit():
        target_id = int(args)
    else:
        target_id = get_id_by_username(args)

    if not target_id:
        await message.answer(f"❌ Пользователь {args} не найден в базе.")
        return

    unban_user_db(target_id)
    await message.answer(f"✅ Пользователь <code>{target_id}</code> ({args}) РАЗБАНЕН.")
    
    try:
        await bot.send_message(target_id, "✅ Доступ к боту восстановлен.")
    except:
        pass

# ================= ОБЫЧНЫЕ ХЕНДЛЕРЫ =================
@dp.message(F.chat.type == "private", CommandStart())
async def cmd_start(message: Message):
    add_user_to_db(message.from_user.id, message.from_user.username)
    
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы забанены. Обратитесь к админу.")
        return

    await message.answer(
        "Приветствую.\n"
        "Скинь сюда человека и текст в одном сообщении\n"
        "(фото/видео и текст должны быть в одном посте).\n\n"
        "Отправляя материал, вы подтверждаете, что несёте полную ответственность за его содержание и имеете право на его распространение."
    )

# РАССЫЛКА
@dp.message(F.chat.type == "private", Command("post"))
async def cmd_post(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Ошибка. Пиши: `/post Текст`")
        return

    text = parts[1]
    users = get_all_users()
    await message.answer(f"🚀 Рассылка на {len(users)} пользователей...")

    count = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, text)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    
    await message.answer(f"✅ Успешно отправлено: {count}")

# 3. ПЕРЕХВАТЧИК КОММЕНТАРИЕВ
@dp.message(F.chat.id == DISCUSSION_CHAT_ID)
async def handle_discussion_post(message: Message):
    if message.is_automatic_forward and message.forward_from_message_id:
        channel_msg_id = message.forward_from_message_id
        
        if channel_msg_id in pending_comments:
            numbers = pending_comments[channel_msg_id]
            nums_str = "\n".join(numbers)
            comment_text = f"📞 Номер(а) из поста:\n{nums_str}"
            
            try:
                await message.reply(comment_text)
            except Exception as e:
                logging.error(f"Err comment: {e}")
            finally:
                del pending_comments[channel_msg_id]

# 4. ПРИЕМ КОНТЕНТА
@dp.message(F.chat.type == "private", F.content_type.in_({'text', 'photo', 'video'}))
async def handle_content(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Сохраняем и проверяем бан
    add_user_to_db(user_id, username)
    if is_user_banned(user_id):
        await message.answer("⛔ Вы забанены.")
        return

    if message.text and message.text.startswith('/'):
        return

    raw_text = message.text or message.caption or ""
    clean_text, numbers = process_text(raw_text)
    final_text = clean_text + FOOTER_TEXT

    try:
        sent_msg = None

        if (message.photo or message.video) and len(final_text) > 1024:
            await message.answer("❌ Текст слишком длинный (лимит 1024 символа).")
            return

        if message.photo:
            photo_id = message.photo[-1].file_id
            sent_msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=final_text)
        elif message.video:
            video_id = message.video.file_id
            sent_msg = await bot.send_video(chat_id=CHANNEL_ID, video=video_id, caption=final_text)
        else:
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=final_text, disable_web_page_preview=True)

        if numbers and sent_msg:
            pending_comments[sent_msg.message_id] = numbers

        await message.answer("✅ Пост опубликован анонимно.")

        # УВЕДОМЛЕНИЕ АДМИНУ
        user_link = f"@{username}" if username else "без юзернейма"
        alert_text = (
            f"📝 <b>Новый пост!</b>\n"
            f"От: {message.from_user.full_name}\n"
            f"ID: <code>{user_id}</code>\n"
            f"User: {user_link}\n\n"
            f"Бан: /ban \n\n"
            f"Разбан: /unban \n\n"
        )
        try:
            await bot.send_message(ADMIN_ID, alert_text)
        except:
            pass

    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            await message.answer(f"❌ Ошибка ID каналов.")
        else:
            await message.answer(f"❌ Ошибка ТГ: {e}")
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("❌ Ошибка.")

# ================= ЗАПУСК =================

async def main():
    init_db()
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
