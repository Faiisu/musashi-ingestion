FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY simulations ./simulations
RUN pip install --no-cache-dir . && useradd --system --uid 10001 --home /app musashi && mkdir /data && chown 10001:10001 /data
USER musashi
ENV MUSASHI_BIND=127.0.0.1 MUSASHI_PORT=8080 MUSASHI_DATA_DIR=/data
CMD ["musashi-ingestion"]
