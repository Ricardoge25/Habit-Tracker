# Dockerfile - Backend
FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Evitar que Python genere  archivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1 

# Instalar dependencias del sistema necesarias para psycopg2 y compilación
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código del backend
COPY  . .

# Exponer el puerto
EXPOSE 8000

# Comando de inicio
RUN pip install watchdog
CMD [ "python", "manage.py", "runserver", "0.0.0.0:8000" ]