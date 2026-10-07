FROM python:3.12-slim

# Sem isso, print() fica bufferizado dentro do container e nao aparece nos logs
# do Docker/Portainer ate o buffer encher ou o processo encerrar.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Binario do Tesseract + pacote de idioma portugues, usados pelo OCR local
# (app/utils/ocr.py). O ingles ja vem junto do pacote base. Se preferir uma imagem
# menor, remova daqui: o bot detecta a ausencia e desliga o OCR sozinho.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

# Sem root: Pillow e Tesseract abrem imagem enviada por qualquer pessoa.
RUN useradd --system --uid 1000 --no-create-home bot \
    && mkdir -p /app/data && chown bot /app/data
USER bot

VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
