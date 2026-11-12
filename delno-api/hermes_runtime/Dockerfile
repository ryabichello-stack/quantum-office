# DELNO tenant Hermes runtime — pinned NousResearch/hermes-agent
# Build: docker build -t delno-hermes-runtime:v0.23.1 -f Dockerfile .
FROM python:3.12-slim-bookworm

ARG HERMES_AGENT_GIT_REF=v0.23.1
ARG HERMES_AGENT_GIT_URL=https://github.com/NousResearch/hermes-agent.git

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/hermes-agent
RUN git clone --depth 1 --branch "${HERMES_AGENT_GIT_REF}" "${HERMES_AGENT_GIT_URL}" . \
 && pip install --no-cache-dir -U pip \
 && (pip install --no-cache-dir -e ".[all]" || pip install --no-cache-dir -e .)

ENV HERMES_HOME=/data/hermes \
    API_SERVER_ENABLED=true \
    API_SERVER_HOST=0.0.0.0 \
    API_SERVER_PORT=8642 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data/hermes
WORKDIR /data/hermes
EXPOSE 8642

# Entry: prefer hermes gateway/api if present; fallback documented in README.
COPY entrypoint.sh /usr/local/bin/delno-hermes-entrypoint
RUN chmod +x /usr/local/bin/delno-hermes-entrypoint
ENTRYPOINT ["/usr/local/bin/delno-hermes-entrypoint"]
