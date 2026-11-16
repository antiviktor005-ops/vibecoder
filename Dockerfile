FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 worker
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
USER worker
CMD ["python", "-m", "app.main"]
