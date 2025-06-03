FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y cron

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY update_status.py .

CMD ["python", "-u", "update_status.py"]
