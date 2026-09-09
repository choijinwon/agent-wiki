# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "${APP_GID}" knowledge \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin knowledge

WORKDIR /app
COPY knowledge_agent /app/knowledge_agent
RUN mkdir -p /data && chown -R "${APP_UID}:${APP_GID}" /app /data

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KNOWLEDGE_HOST=0.0.0.0 \
    KNOWLEDGE_PORT=8090 \
    KNOWLEDGE_DATA_DIR=/data
USER ${APP_UID}:${APP_GID}
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/health', timeout=2)"
CMD ["python", "-m", "knowledge_agent.web"]
