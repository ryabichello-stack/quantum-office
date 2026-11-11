FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY allowlist.py delivery.py main.py models.py sources.py ./
COPY README.md ./

RUN mkdir -p /data/assets \
    && printf '%s\n' "DELNO files broker — local allowlist root" > /data/assets/README.txt

ENV FILES_LOCAL_ALLOWLIST=/data/assets
ENV FILES_MAX_BYTES=47185920

EXPOSE 8015
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8015"]
