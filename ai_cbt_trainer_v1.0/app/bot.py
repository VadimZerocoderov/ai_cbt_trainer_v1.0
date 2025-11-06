# app/bot.py
# ============================================================
# AI_CBT_Trainer — Telegram Bot (DEMO, safe for public GitHub)
# Public demo: offline generation (no external LLM/API calls)
# Full stable build kept privately as: app/bot_v1.0.py
# ============================================================

import asyncio
import os
import re
from typing import List, Tuple, Dict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command

# ---- ENV (опционально)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ---- Константы / темы
TOPICS: List[str] = [
    "Прокрастинация и самокритика",
    "Повышенная тревожность (перед выступлениями)",
    "Страх неуспеха/неудачи",
    "Чувство вины",
    "Ревность и тревога в отношениях",
    "Страх перемен",
    "Проблемы выбора",
    "Трудности в отношениях с близкими",
    "Заниженная самооценка",
    "Психологическое выгорание",
    "Своя тема",
]

# ---- Состояние сессий (простая in-memory карта)
# USER_STATE[user_id] = {"topic": str, "history": list[dict], "step": int, "options": list[str]}
USER_STATE: Dict[int, Dict] = {}
SLEEP_USERS: set[int] = set()       # «сон» после /end до следующего /start
RUNNING_TASKS: Dict[int, asyncio.Task] = {}

# ---- UI клавиатуры
def topics_kb() -> InlineKeyboardMarkup:
    rows = []
    for i, t in enumerate(TOPICS, start=1):
        # показываем «1. Прокрастинация…»
        rows.append([InlineKeyboardButton(text=f"{i}. {t}", callback_data=f"topic_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="A", callback_data="choice_A"),
         InlineKeyboardButton(text="B", callback_data="choice_B"),
         InlineKeyboardButton(text="C", callback_data="choice_C"),
         InlineKeyboardButton(text="D", callback_data="choice_D")]
    ])

# ---- Нормализация A–D (латиница/кириллица)
def normalize_choice(s: str) -> str:
    s = s.strip().lower()
    mapping = {"a": "a", "а": "a", "b": "b", "в": "b", "c": "c", "с": "c", "d": "d", "д": "d"}
    return mapping.get(s, "")

# ---- DEMO-«генерация» (без LLM) -------------------------------------------
# Возвращает (реплика клиента, варианты ответов A–D)
def demo_generate_turn(topic: str, history: List[Dict], user_reply: str = "") -> Tuple[str, List[str]]:
    step = len(history)

    # Небольшие заготовки по шагам — достаточно для демонстрации логики
    openings = {
        "Прокрастинация и самокритика": "Я всё откладываю и ругаю себя за это. Кажется, я ни на что не способен.",
        "Страх неуспеха/неудачи": "Если у меня не получится, все подумают, что я бездарность.",
    }
    generic_open = "Мне трудно справляться с мыслями — они сразу катятся в негатив."

    # Первый ход — новая реплика «клиента» на основе темы
    if step == 0:
        client_line = openings.get(topic, generic_open)
    else:
        # На следующих шагах упрощённая логика: отражаем выбор и даём новую мысль
        tail = {
            "a": "Какие факты указывают на это? Наверное, я не всё учитываю.",
            "b": "С одной стороны, это звучит логично… но сомнения остаются.",
            "c": "Ну, может быть… Хотя не уверен(а).",
            "d": "Нет, мне кажется, это не про меня. Я просто не справляюсь.",
        }
        key = normalize_choice(user_reply) or "b"
        client_line = tail.get(key, tail["b"])

    # Варианты ответов терапевта (A–D) — «вероятные», по убыванию корректности
    options = [
        "Давайте заметим автоматическую мысль и проверим её точность: какие факты «за» и «против»?",
        "Похоже, вы очень строги к себе — можно ли переформулировать с большей доброжелательностью?",
        "Так бывает со многими — возможно, стоит просто «вписать» маленький шаг в план на сегодня.",
        "Нужно просто перестать лениться и собраться.",
    ]
    return client_line, options
# ---------------------------------------------------------------------------

# ---- Бот/диспетчер
BOT_TOKEN = os.getenv("BOT_TOKEN", "REPLACE_ME")
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ---- Хэндлеры
@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    SLEEP_USERS.discard(uid)
    USER_STATE.pop(uid, None)
    await message.answer(
        "Привет! Это демо-версия тренажёра КПТ (без внешних ИИ-сервисов).\n"
        "Выберите тему тренировки:",
        reply_markup=topics_kb(),
    )

@dp.message(Command("end"))
async def cmd_end(message: Message):
    uid = message.from_user.id
    # Останавливаем фоновые задачи, очищаем состояние
    task = RUNNING_TASKS.pop(uid, None)
    if task and not task.done():
        task.cancel()
    USER_STATE.pop(uid, None)
    SLEEP_USERS.add(uid)
    await message.answer(
        "Конец сессии. Для запуска нового чата нажмите /start",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.callback_query(F.data.startswith("topic_"))
async def on_topic(callback):
    uid = callback.from_user.id
    if uid in SLEEP_USERS:
        await callback.answer("Нажмите /start для новой сессии")
        return

    # Определяем тему
    try:
        num = int(callback.data.split("_", 1)[1])
        if not (1 <= num <= len(TOPICS)):
            await callback.answer("Некорректная тема")
            return
        topic = TOPICS[num - 1]
    except Exception:
        await callback.answer("Некорректная тема")
        return

    # «Своя тема» → оставим как текст
    if num == len(TOPICS):
        topic = "Своя тема (демо)"

    USER_STATE[uid] = {"topic": topic, "history": [], "step": 0, "options": []}
    await callback.message.answer(f"Вы выбрали тему: {topic}")

    # Первый ход
    client_line, options = demo_generate_turn(topic, USER_STATE[uid]["history"])
    USER_STATE[uid]["history"].append({"client": client_line})
    USER_STATE[uid]["options"] = options
    USER_STATE[uid]["step"] = 1

    await callback.message.answer(f"Клиент: {client_line}\n(Ответьте и продолжим)")
    await callback.message.answer(
        "Варианты ответов терапевта (A–D):\n\n"
        f"A) {options[0]}\n\nB) {options[1]}\n\nC) {options[2]}\n\nD) {options[3]}",
        reply_markup=choice_kb(),
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("choice_"))
async def on_choice(callback):
    uid = callback.from_user.id
    state = USER_STATE.get(uid)
    if not state or uid in SLEEP_USERS:
        await callback.answer("Нажмите /start для новой сессии")
        return

    # Нормализуем выбор
    letter = callback.data.split("_", 1)[1].lower()  # 'a' | 'b' | 'c' | 'd'
    letter = normalize_choice(letter)

    # Следующий ход (демо-логика)
    topic = state["topic"]
    history = state["history"]

    # Считаем этот ответ «принятым» и строим новую клиентскую реплику
    client_line, options = demo_generate_turn(topic, history, user_reply=letter)
    history.append({"client": client_line})
    state["options"] = options
    state["step"] += 1

    await callback.message.answer(f"Спасибо, принято. Продолжаем.")
    await callback.message.answer(f"Клиент: {client_line}")
    await callback.message.answer(
        "Варианты ответов терапевта (A–D):\n\n"
        f"A) {options[0]}\n\nB) {options[1]}\n\nC) {options[2]}\n\nD) {options[3]}",
        reply_markup=choice_kb(),
    )
    await callback.answer()

# Фолбэк-хэндлер на текст (подсказываем, что делать)
@dp.message(F.text)
async def dialog_flow(message: Message):
    if message.text.strip().lower() in ("/start", "start"):
        return  # /start уже обрабатывается отдельно
    await message.answer("Выберите тему через /start, затем используйте кнопки A–D. Для завершения — /end.")

# ---- Точка входа
async def main():
    print("Bot polling started (DEMO)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
