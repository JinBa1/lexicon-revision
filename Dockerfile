FROM python:3.12-slim AS prod-base
WORKDIR /app
ENV PIP_DEFAULT_TIMEOUT=200

FROM prod-base AS prod
ENV APP_ENV=prod
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim AS dev-base
WORKDIR /app
ENV PIP_DEFAULT_TIMEOUT=200
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

FROM dev-base AS dev
COPY requirements.txt requirements-local.txt requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-local.txt -r requirements-dev.txt
COPY . .
CMD ["uvicorn", "src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
