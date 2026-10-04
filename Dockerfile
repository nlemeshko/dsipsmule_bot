# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Оптимизация зависимостей
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Установим системные зависимости для http/ssl и т.п.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем только зависимости для кеширования слоёв
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Копируем исходники
COPY . /app
RUN chown -R 10001:10001 /app/data

# Задаем переменные окружения (могут перекрываться при запуске)
# ENV BOT_TOKEN="" \
#     ADMINS="" \
#     CHARACTER_AI_TOKEN="" \
#     CHARACTER_ID="" \
#     CHARACTER_VOICE_ID=""

# Запуск
EXPOSE 8080
CMD ["python", "bot.py"]
