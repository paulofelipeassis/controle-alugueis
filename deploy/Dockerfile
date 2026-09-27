# Uma imagem só para os três serviços (web, mcp, backup).
FROM python:3.12-slim

# rclone: envio do backup para o Google Drive.
RUN apt-get update && apt-get install -y --no-install-recommends rclone ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sistema/requirements.txt sistema/requirements.txt
RUN pip install --no-cache-dir -r sistema/requirements.txt
COPY sistema/ sistema/
COPY scripts/ scripts/

# Roda como root de propósito: a pasta de documentos é compartilhada com o Hermes
# e o File Browser, e assim ninguém esbarra em permissão de arquivo.
ENV DB_PATH=/dados/alugueis.db \
    DOCS_DIR=/documentos \
    BACKUP_DIR=/dados/backups \
    RCLONE_CONFIG=/dados/rclone/rclone.conf \
    TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "sistema.web:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
