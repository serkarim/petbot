# Используем официальный образ с уже установленным Chromium
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Оптимизация памяти для Railway
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Предварительно устанавливаем браузер (если образ чистый)
RUN playwright install chromium --with-deps 2>/dev/null || true

# Запускаем через Procfile-совместимую команду
CMD ["python", "main.py"]