# Используем официальный Python образ
FROM python:3.13

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlalchemy pydantic jinja2 requests

# Создаем директорию для шаблонов (если она не существует)
RUN mkdir -p templates

# Экспонируем порт приложения
EXPOSE 8000

# Одноступенчатый запуск приложения
CMD ["python", "main.py"]
