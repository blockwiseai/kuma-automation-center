FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade -r ./requirements.txt

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "-u", "main.py"]
