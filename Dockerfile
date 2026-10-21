# accounti — Abbild für Anwendung und geplanten Lauf (docs/betrieb.md).
# Geheimnisse gehören nie ins Abbild: sie kommen zur Laufzeit aus der Umgebung.

FROM python:3.12-slim-bookworm AS bau
WORKDIR /bau
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim-bookworm
# OCR für Scans (Tesseract, deutsch); ohne: --build-arg OCR=nein
ARG OCR=ja
RUN if [ "$OCR" = "ja" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-deu \
        && rm -rf /var/lib/apt/lists/*; \
    fi \
    && useradd --system --uid 10001 --user-group --home-dir /arbeit --create-home accounti \
    && mkdir -p /arbeit/daten/belege /arbeit/config \
    && chown -R accounti:accounti /arbeit
COPY --from=bau /install /usr/local
# Migrationen für bestehende Datenbanken: alembic -c /app/alembic.ini upgrade head
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

WORKDIR /arbeit
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCOUNTI_KONFIG=/arbeit/config/accounti.yaml \
    ACCOUNTI_ARCHIV=/arbeit/daten/belege
USER accounti
VOLUME ["/arbeit/daten"]
EXPOSE 8400
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8400/gesund', timeout=4).status == 200 else 1)"]
ENTRYPOINT ["accounti"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8400"]
