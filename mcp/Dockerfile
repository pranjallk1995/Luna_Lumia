FROM python:3.12-slim
WORKDIR /workspace/mcp
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_LINK_MODE=copy
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --system -r requirements.txt
COPY app ./app
COPY tests ./tests
EXPOSE 8000
CMD ["python", "-m", "app.main"]

