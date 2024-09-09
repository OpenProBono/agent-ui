FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /api

RUN apt-get update

COPY requirements.txt /api/requirements.txt

RUN pip install -r requirements.txt

COPY static /api/static

COPY templates /api/templates

COPY app.py /api/app.py

CMD gunicorn -t 120 app:app