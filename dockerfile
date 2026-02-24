FROM python:3.12-slim

# Prevents Python from writing pyc files and buffers
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but common)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install python deps
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project (including db.sqlite3 if it's in the root)
COPY . /app/

# (Optional but recommended) collect static if you use it
# RUN python manage.py collectstatic --noinput

EXPOSE 8000

# For dev-style run (fine for assessment / local)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]