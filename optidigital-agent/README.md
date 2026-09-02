<div align="center">

# OptiDigital Agent 🤖

**AI-агент для автоматичного пошуку, оцінки та відповіді на фріланс-замовлення**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template)

</div>

---

## What is this?

OptiDigital Agent — це автономний Telegram-бот, який кожні 15 хвилин переглядає нові проєкти на Freelancehunt, оцінює їх за допомогою GPT-4o за 10-бальною шкалою та надсилає у ваш Telegram-чат лише ті замовлення, які варті уваги — разом із готовим відгуком.

Ніякого ручного моніторингу. Лише релевантні ліди.

---

## Features

- **Автоматичний парсинг** — перевіряє Freelancehunt кожні 15 хвилин
- **AI-скоринг** — GPT-4o оцінює бюджет, відповідність спеціалізації, якість ТЗ і конкуренцію
- **Готові відгуки** — генерує відповідь від імені агентства одразу після оцінки
- **Telegram-сповіщення** — лише замовлення вище мінімального порогу (налаштовується)
- **Тижневий звіт** — щонеділі о 09:00 (Kyiv) підбиває підсумки тижня
- **Керування зі смартфона** — команди `/stats`, `/settings` прямо в боті
- **Захист від дублів** — база даних запам'ятовує вже оброблені замовлення
- **Retry + rate-limit handling** — стабільна робота навіть при обмеженнях API

---

## Tech Stack

| Компонент | Технологія |
|---|---|
| Мова | Python 3.11 |
| Telegram Bot | aiogram 3.x |
| AI | OpenAI GPT-4o |
| База даних | PostgreSQL (asyncpg + SQLAlchemy) |
| Планувальник | APScheduler |
| HTTP-клієнт | httpx |
| Конфігурація | pydantic-settings |
| Деплой | Railway (Nixpacks) |

---

## Setup

### 1. Клонуй репозиторій

```bash
git clone https://github.com/your-username/optidigital-agent.git
cd optidigital-agent
```

### 2. Створи віртуальне середовище та встанови залежності

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Налаштуй змінні середовища

```bash
cp .env.example .env
# Відкрий .env та заповни всі значення
```

### 4. Запуск

```bash
python bot/main.py
```

---

## Environment Variables

| Змінна | Опис | Де отримати |
|---|---|---|
| `TELEGRAM_TOKEN` | Токен бота | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_CHAT_ID` | ID чату для сповіщень | [@userinfobot](https://t.me/userinfobot) |
| `OPENAI_API_KEY` | Ключ OpenAI API | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `FREELANCEHUNT_TOKEN` | API-токен Freelancehunt | Профіль → Налаштування → API |
| `DATABASE_URL` | URL PostgreSQL бази | `postgresql+asyncpg://user:pass@host/db` |

Приклад `.env`:

```env
TELEGRAM_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=123456789
OPENAI_API_KEY=sk-...
FREELANCEHUNT_TOKEN=your_freelancehunt_token
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/optidigital
```

---

## Deploy to Railway

Найпростіший спосіб — одна кнопка:

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template)

### Або вручну:

1. **"New Project" → "Deploy from GitHub repo"** → підключи цей репозиторій
2. Додай PostgreSQL: **"+ New" → "Database" → "Add PostgreSQL"**
3. Перейди у **Variables** і додай усі змінні з таблиці вище
4. `DATABASE_URL` Railway підставить автоматично — лише заміни `postgresql://` → `postgresql+asyncpg://`
5. Railway запустить бота через `railway.json` автоматично після кожного push

---

## Project Structure

```
optidigital-agent/
├── bot/            # Telegram-бот (aiogram 3): handlers, keyboards
├── db/             # SQLAlchemy моделі та CRUD
├── ai/             # OpenAI scorer та writer
├── parser/         # Freelancehunt API клієнт
├── scheduler.py    # APScheduler завдання (15 хв + тижневий звіт)
├── config.py       # Pydantic Settings (читає .env)
├── Procfile        # Railway / Heroku entry point
└── railway.json    # Railway deploy config
```

---

<div align="center">

Зроблено командою **OptiDigital**

</div>
