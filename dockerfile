FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1

COPY Pipfile Pipfile.lock /app/
WORKDIR /app

RUN apk add --no-cache --upgrade build-base linux-headers && \
    pip install --upgrade pip && \
    pip install pipenv && \
    pipenv sync

COPY . /app

RUN adduser --disabled-password --no-create-home django

USER django

CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]