FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY templates/ templates/
COPY static/ static/

ENV PORT=8001
ENV SYNC_SERVICE_URL=http://localhost:8000

EXPOSE 8001

CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "2", "--chdir", "src", "app:app"]
