FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py caldav_client.py conference_client.py mailer_client.py ./
EXPOSE 8014
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8014"]
