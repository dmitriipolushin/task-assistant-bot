FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV PYTHONPATH=/app
ENV DATABASE_PATH=/app/data/bot.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sqlite3; sqlite3.connect('/app/data/bot.db').execute('SELECT 1')" || exit 1

CMD ["python", "main.py"]



