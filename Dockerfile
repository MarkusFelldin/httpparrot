FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV SSL_CERT_FILE=/usr/local/lib/python3.11/site-packages/certifi/cacert.pem

COPY . .

EXPOSE 8080

CMD ["gunicorn", "index:app", "--bind", "0.0.0.0:8080", "--preload", "--workers", "2"]
