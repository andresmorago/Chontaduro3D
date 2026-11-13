FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Bogota

WORKDIR /app

# postgresql-client trae pg_dump: lo usa app/migrar.py para respaldar antes de migrar.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000


# Desarrollo: el código llega montado por volumen, así que se instala editable.
FROM base AS dev
RUN pip install --upgrade pip && pip install -e ".[dev]"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# Producción: el código va dentro de la imagen. `arrancar.sh` migra (con respaldo
# previo) y luego ejecuta el CMD. El entrypoint solo vive en esta etapa.
FROM base AS runtime
RUN pip install --upgrade pip && pip install "." \
    && useradd --create-home --uid 1000 app \
    && chmod +x /app/arrancar.sh \
    && chown -R app:app /app
USER app
ENTRYPOINT ["/app/arrancar.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
