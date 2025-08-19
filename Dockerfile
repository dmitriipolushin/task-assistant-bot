FROM python:3.11-slim

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data && chmod 755 /data

ENV PYTHONPATH=/app
ENV DATABASE_PATH=/data/bot.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sqlite3; sqlite3.connect('/data/bot.db').execute('SELECT 1')" || exit 1

WORKDIR /app
CMD ["python", "main.py"]



