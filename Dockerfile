FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock alembic.ini ./
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev
COPY --from=frontend /frontend/dist ./frontend/dist/
ENV PATH="/app/.venv/bin:$PATH" APP_HOST=0.0.0.0 APP_PORT=8765
EXPOSE 8765
CMD ["xresearch", "api"]
