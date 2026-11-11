FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py invites.py telemost.py yandex_oauth.py ./
ENV TELEMOST_STUB_WHEN_UNAUTH=true
EXPOSE 8016
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8016"]
