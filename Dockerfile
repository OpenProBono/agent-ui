FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /api

RUN apt-get update

COPY requirements.txt /api/requirements.txt

RUN pip install -r requirements.txt

COPY templates /api/templates

COPY app.py /api/app.py

COPY app_helper.py /api/app_helper.py

COPY static /api/static

CMD gunicorn -t 120 app:app