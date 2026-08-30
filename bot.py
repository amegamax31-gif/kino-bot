import asyncio
import logging
import sqlite3
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

API_TOKEN = os.getenv('BOT_TOKEN')

# Instagram va YouTube havolalari
INSTAGRAM_LINK = "https://instagram.com/sizning_sahifangiz"
YOUTUBE_LINK = "https://www.youtube.com/channel/UC_9A2iaSGLvswTbQfX3Zvgw"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Ma'lumotlar bazasini ulash
conn = sqlite3.connect('kinolar.db')
cursor = conn.cursor()

# Oddiy (bitta qismli) kinolar jadvali
cursor.execute('''
CREATE TABLE IF NOT EXISTS movies (
    code TEXT PRIMARY KEY,
    file_id TEXT,
    caption TEXT
)
''')

# Seriallar haqida umumiy ma'lumot (poster + tavsif)
cursor.execute('''
CREATE TABLE IF NOT EXISTS series (
    code TEXT PRIMARY KEY,
    poster_file_id TEXT,
    info_caption TEXT
)
''')

# Serial qismlari
cursor.execute('''
CREATE TABLE IF NOT EXISTS episodes (
    series_code TEXT,
    episode_number INTEGER,
    file_id TEXT,
    PRIMARY KEY (series_code, episode_number)
)
''')

# Obuna tasdiqlagan foydalanuvchilar
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💜📱💫 𝑰𝒏𝒔𝒕𝒂𝒈𝒓𝒂𝒎", url=INSTAGRAM_LINK)],
        [InlineKeyboardButton(text="🎬🔴🔥 𝒀𝒐𝒖𝑻𝒖𝒃𝒆", url=YOUTUBE_LINK)],
        [InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="confirm_sub")]
    ])


def episodes_keyboard(series_code: str):
    cursor.execute(
        "SELECT episode_number FROM episodes WHERE series_code = ? ORDER BY episode_number",
        (series_code,)
    )
    numbers = [row[0] for row in cursor.fetchall()]

    buttons = []
    row = []
    for i, num in enumerate(numbers, start=1):
        row.append(InlineKeyboardButton(text=str(num), callback_data=f"ep_{series_code}_{num}"))
        if i % 5 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


# QISM TANLANGANDA VIDEO YUBORISH
@dp.callback_query(F.data.startswith("ep_"))
async def send_episode(callback: CallbackQuery):
    _, series_code, episode_number = callback.data.split("_")

    cursor.execute(
        "SELECT file_id FROM episodes WHERE series_code = ? AND episode_number = ?",
        (series_code, int(episode_number))
    )
    result = cursor.fetchone()

    if result:
        file_id = result[0]
        await callback.message.answer_video(
            video=file_id,
            caption=f"🎬 {episode_number}-qism"
        )
    else:
        await callback.answer("Bu qism topilmadi.", show_alert=True)
        return

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

    code = message.text

    # 1) Avval oddiy (bitta qismli) kino bazasidan qidiramiz
    cursor.execute("SELECT file_id, caption FROM movies WHERE code = ?", (code,))
    result = cursor.fetchone()
    if result:
        file_id, caption = result
        await message.reply_video(video=file_id, caption=caption)
        return

    # 2) Bo'lmasa, serial bazasidan qidiramiz
    cursor.execute("SELECT poster_file_id, info_caption FROM series WHERE code = ?", (code,))
    series_result = cursor.fetchone()
    if series_result:
        poster_file_id, info_caption = series_result
        keyboard = episodes_keyboard(code)

        if poster_file_id:
            await message.answer_photo(
                photo=poster_file_id,
                caption=info_caption,
                reply_markup=keyboard
            )
        else:
            await message.answer(
                info_caption or "Kerakli qismni tanlang:",
                reply_markup=keyboard
            )
        return

    await message.reply("Afsuski, bu kod ostida kino topilmadi. 😔")


# ADMIN UCHUN: Oddiy kino qo'lda qo'shish
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


# KANALGA POST QILINGANDA AVTOMATIK QO'SHISH
# Poster (rasm) uchun caption formati:      Film kodi: 870 ...
# Serial qismi (video) uchun caption:       Kod: 870\nQism: 3
# Oddiy kino (video) uchun caption:         Kod: 101   (Qism yo'q)
@dp.channel_post()
async def auto_add_from_channel(message: types.Message):
    caption = message.caption or ""

    # --- Serial posteri (rasm) ---
    if message.photo:
        poster_match = re.search(r"Film kodi:\s*(\d+)", caption)
        if poster_match:
            series_code = poster_match.group(1)
            poster_file_id = message.photo[-1].file_id

            cursor.execute(
                "INSERT INTO series (code, poster_file_id, info_caption) VALUES (?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET poster_file_id=excluded.poster_file_id, "
                "info_caption=excluded.info_caption",
                (series_code, poster_file_id, caption)
            )
            conn.commit()
            logging.info(f"Serial posteri saqlandi: kod={series_code}")
        return

    # --- Video (oddiy kino yoki serial qismi) ---
    if message.video:
        code_match = re.search(r"Kod:\s*(\d+)", caption)
        if not code_match:
            return

        code = code_match.group(1)
        file_id = message.video.file_id
        episode_match = re.search(r"Qism:\s*(\d+)", caption)

        if episode_match:
            # Serial qismi sifatida saqlaymiz
            episode_number = int(episode_match.group(1))
            cursor.execute(
                "INSERT INTO episodes (series_code, episode_number, file_id) VALUES (?, ?, ?) "
                "ON CONFLICT(series_code, episode_number) DO UPDATE SET file_id=excluded.file_id",
                (code, episode_number, file_id)
            )
            conn.commit()
            logging.info(f"Serial qismi saqlandi: kod={code}, qism={episode_number}")
        else:
            # Oddiy kino sifatida saqlaymiz
            try:
                cursor.execute("INSERT INTO movies VALUES (?, ?, ?)", (code, file_id, caption))
                conn.commit()
            except sqlite3.IntegrityError:
                cursor.execute(
                    "UPDATE movies SET file_id=?, caption=? WHERE code=?",
                    (file_id, caption, code)
                )
                conn.commit()
            logging.info(f"Oddiy kino saqlandi: kod={code}")


# Istalgan videoni botga yuborsangiz yoki forward qilsangiz, file_id chiqadi
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
