FROM node:24-bookworm-slim AS web
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY --from=web /web/dist frontend/dist/
RUN useradd --create-home app && mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && python -m backend.app.seed && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
