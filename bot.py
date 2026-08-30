import asyncio
import logging
import sqlite3
import os
API_TOKEN = os.getenv('BOT_TOKEN')
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# API_TOKEN = 'Buyerda TOKEN'

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

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.reply("Salom! Kino kodini yuboring, men sizga kinoni topib beraman.")

# KOD QABUL QILISH (Faqat raqamlar uchun)
@dp.message(F.text.isdigit())
async def get_movie(message: types.Message):
    movie_code = message.text
    
    cursor.execute("SELECT file_id, caption FROM movies WHERE code = ?", (movie_code,))
    result = cursor.fetchone()
    
    if result:
        file_id, caption = result
        await message.reply_video(video=file_id, caption=caption)
    else:
        await message.reply("Afsuski, bu kod ostida kino topilmadi. 😔")

# ADMIN UCHUN: Yangi kino qo'shish
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

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

# Istalgan videoni botga yuborsangiz yoki forward qilsangiz, sizga uning file_id sini beradi
@dp.message(F.video)
async def get_video_file_id(message: types.Message):
    file_id = message.video.file_id
    await message.reply(f"🎬 Videoning file_id'si:\n\n`{file_id}`\n\nUni nusxalab oling va /add_movie buyrug'i orqali bazaga qo'shing.")

if __name__ == '__main__':
 asyncio.run(main())
