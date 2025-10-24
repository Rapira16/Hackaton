# Используем официальный Python-образ
FROM python:3.13

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем все файлы проекта
COPY . /app

# Устанавливаем зависимости
RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy pydantic requests jinja2

# Открываем порт FastAPI
EXPOSE 8000

# Команда запуска приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
