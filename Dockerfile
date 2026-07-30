FROM python:3.12-slim

# Sem isso, print() fica bufferizado dentro do container e nao aparece nos logs
# do Docker/Portainer ate o buffer encher ou o processo encerrar.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
