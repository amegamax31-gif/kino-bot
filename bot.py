import asyncio
import logging
import sqlite3
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

API_TOKEN = os.getenv('BOT_TOKEN')

# Instagram va YouTube havolalari (o'zingiznikiga almashtiring)
INSTAGRAM_LINK = "https://www.youtube.com/channel/UC_9A2iaSGLvswTbQfX3Zvgw"
YOUTUBE_LINK = "https://www.instagram.com/kino.taime/"

# Bot va Dispatcher obyektlarini yaratish
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Ma'lumotlar bazasini ulash
conn = sqlite3.connect('kinolar.db')
cursor = conn.cursor()

# Kinolar jadvalini yaratish
cursor.execute('''
CREATE TABLE IF NOT EXISTS movies (
    code TEXT PRIMARY KEY,
    file_id TEXT,
    caption TEXT
)
''')
conn.commit()

# Obuna bo'lgan foydalanuvchilarni saqlash jadvali (doimiy saqlanadi)
cursor.execute('''
CREATE TABLE IF NOT EXISTS confirmed_users (
    user_id INTEGER PRIMARY KEY
)
''')
conn.commit()


def is_confirmed(user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM confirmed_users WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None


def confirm_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO confirmed_users VALUES (?)", (user_id,))
    conn.commit()


def subscribe_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM_LINK)],
        [InlineKeyboardButton(text="▶️ YouTube", url=YOUTUBE_LINK)],
        [InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="confirm_sub")]
    ])
    return kb


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if is_confirmed(message.from_user.id):
        await message.reply("Salom! Kino kodini yuboring, men sizga kinoni topib beraman.")
    else:
        await message.answer(
            "Botdan foydalanish uchun quyidagi sahifalarga obuna bo'ling:",
            reply_markup=subscribe_keyboard()
        )


@dp.callback_query(F.data == "confirm_sub")
async def confirm_subscription(callback: CallbackQuery):
    confirm_user(callback.from_user.id)
    await callback.message.edit_text("Rahmat! Endi kino kodini yuboring. 🎬")
    await callback.answer()


# KOD QABUL QILISH (Faqat raqamlar uchun)
@dp.message(F.text.isdigit())
async def get_movie(message: types.Message):
    if not is_confirmed(message.from_user.id):
        await message.answer(
            "Iltimos, avval obuna bo'ling:",
            reply_markup=subscribe_keyboard()
        )
        return

    movie_code = message.text

    cursor.execute("SELECT file_id, caption FROM movies WHERE code = ?", (movie_code,))
    result = cursor.fetchone()

    if result:
        file_id, caption = result
        await message.reply_video(video=file_id, caption=caption)
    else:
        await message.reply("Afsuski, bu kod ostida kino topilmadi. 😔")


# ADMIN UCHUN: Yangi kino qo'shish (qo'lda)
@dp.message(Command("add_movie"))
async def add_movie(message: types.Message):
    args = message.text.split(maxsplit=3)
    if len(args) >= 3:
        code = args[1]
        file_id = args[2]
        caption = args[3] if len(args) == 4 else ""

        try:
            cursor.execute("INSERT INTO movies VALUES (?, ?, ?)", (code, file_id, caption))
            conn.commit()
            await message.reply(f"Kino muvaffaqiyatli qo'shildi! Kod: {code}")
        except sqlite3.IntegrityError:
            await message.reply("Bu kod bilan allaqachon kino kiritilgan!")
    else:
        await message.reply("Xato format. Ishlatish: /add_movie [kod] [file_id] [tavsif]")


# KANALGA POST QILINGAN VIDEONI AVTOMATIK QO'SHISH
@dp.channel_post(F.video)
async def auto_add_from_channel(message: types.Message):
    caption = message.caption or ""
    match = re.search(r"Kod:\s*(\d+)", caption)

    if not match:
        return  # kodsiz postlarni e'tiborsiz qoldiramiz

    code = match.group(1)
    file_id = message.video.file_id

    try:
        cursor.execute("INSERT INTO movies VALUES (?, ?, ?)", (code, file_id, caption))
        conn.commit()
        logging.info(f"Kanal orqali kino qo'shildi: kod={code}")
    except sqlite3.IntegrityError:
        cursor.execute("UPDATE movies SET file_id=?, caption=? WHERE code=?", (file_id, caption, code))
        conn.commit()
        logging.info(f"Kanal orqali kino yangilandi: kod={code}")


# Istalgan videoni botga yuborsangiz yoki forward qilsangiz, sizga uning file_id sini beradi
@dp.message(F.video)
async def get_video_file_id(message: types.Message):
    file_id = message.video.file_id
    await message.reply(
        f"🎬 Videoning file_id'si:\n\n`{file_id}`\n\n"
        f"Uni nusxalab oling va /add_movie buyrug'i orqali bazaga qo'shing."
    )


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
