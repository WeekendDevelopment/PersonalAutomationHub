# One image for all three services (api, worker, bot).
# docker-compose.yml starts it three times with a different command each.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

COPY config ./config

# Do not run as root inside the container.
RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "newshub.api:app", "--host", "0.0.0.0", "--port", "8000"]
