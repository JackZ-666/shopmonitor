FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    SHOPMONITOR_MONITOR=1 \
    SHOPMONITOR_HOST=0.0.0.0 \
    SHOPMONITOR_PORT=8000

EXPOSE 8000

CMD ["python", "run_api.py"]
