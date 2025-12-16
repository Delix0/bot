import asyncio
import logging
import re
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
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
    "https://t.me/+9GTEcMHyru5kZWQ0\n"
    "Ссылка для друзей\n\n"
    "https://t.me/+RNj3e09-hqthNmM0\n"
    "Наш чат\n\n"
    "@SlivKhersona_bot\n"
    "Прислать пост"
)

# ================= БАЗА ДАННЫХ =================

def init_db():
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        conn.commit()

def add_user_to_db(user_id: int):
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def get_all_users():
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

# ================= ИНИЦИАЛИЗАЦИЯ =================

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# Словарь для очереди комментариев: {ID_сообщения_в_канале: [список_номеров]}
pending_comments = {}

# ================= ЛОГИКА ОБРАБОТКИ ТЕКСТА =================

def process_text(text: str):
    """Разделяет текст на очищенную версию и найденные номера"""
    if not text:
        return "", []
    
    # Регулярка для телефонов
    phone_pattern = r"(?:\+?38\s*)?0\s*\d{2}[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
    
    found_numbers = re.findall(phone_pattern, text)
    clean_text = re.sub(phone_pattern, " (номер в комментариях) ", text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text, found_numbers

# ================= ХЕНДЛЕРЫ =================

# 1. СТАРТ
@dp.message(F.chat.type == "private", CommandStart())
async def cmd_start(message: Message):
    add_user_to_db(message.from_user.id)
    await message.answer(
        "Приветствую.\n"
        "Скинь сюда человека и текст в одном сообщении\n"
        "(фото/видео и текст должны быть в одном посте)."
    )

# 2. РАССЫЛКА
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

# 3. ПЕРЕХВАТЧИК АВТО-РЕПОСТА В ГРУППЕ (ДЛЯ КОММЕНТАРИЕВ)
@dp.message(F.chat.id == DISCUSSION_CHAT_ID)
async def handle_discussion_post(message: Message):
    """
    Слушает сообщения в группе обсуждения.
    Если это авто-репост из канала и для него есть отложенные номера -> пишет коммент.
    """
    if message.is_automatic_forward and message.forward_from_message_id:
        channel_msg_id = message.forward_from_message_id
        
        if channel_msg_id in pending_comments:
            numbers = pending_comments[channel_msg_id]
            nums_str = "\n".join(numbers)
            comment_text = f"📞 Номер(а) из поста:\n{nums_str}"
            
            try:
                await message.reply(comment_text)
                logging.info(f"Комментарий добавлен к посту {channel_msg_id}")
            except Exception as e:
                logging.error(f"Не удалось оставить комментарий: {e}")
            finally:
                del pending_comments[channel_msg_id]

# 4. ПРИЕМ КОНТЕНТА ОТ ПОЛЬЗОВАТЕЛЯ (ТЕКСТ, ФОТО, ВИДЕО)
@dp.message(F.chat.type == "private", F.content_type.in_({'text', 'photo', 'video'}))
async def handle_content(message: Message):
    add_user_to_db(message.from_user.id)

    if message.text and message.text.startswith('/'):
        return

    # Берем текст из сообщения или подписи (для фото/видео)
    raw_text = message.text or message.caption or ""
    clean_text, numbers = process_text(raw_text)
    final_text = clean_text + FOOTER_TEXT

    try:
        sent_msg = None

        # Проверка длины текста (лимит Телеграм для подписей - 1024)
        if (message.photo or message.video) and len(final_text) > 1024:
            await message.answer("❌ Текст слишком длинный (лимит 1024 символа).")
            return

        # --- ШАГ 1: Публикация в канал ---
        
        # Если это ФОТО
        if message.photo:
            photo_id = message.photo[-1].file_id
            sent_msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=final_text)
        
        # Если это ВИДЕО
        elif message.video:
            video_id = message.video.file_id
            sent_msg = await bot.send_video(chat_id=CHANNEL_ID, video=video_id, caption=final_text)
            
        # Если это просто ТЕКСТ
        else:
            sent_msg = await bot.send_message(chat_id=CHANNEL_ID, text=final_text, disable_web_page_preview=True)

        # --- ШАГ 2: Сохраняем номера в очередь ---
        if numbers and sent_msg:
            pending_comments[sent_msg.message_id] = numbers

        await message.answer("✅ Пост опубликован анонимно.")

    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            await message.answer(f"❌ Ошибка: Бот не нашел канал. Проверь ID и админку.")
        else:
            await message.answer(f"❌ Ошибка Телеграм: {e}")
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("❌ Неизвестная ошибка.")

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