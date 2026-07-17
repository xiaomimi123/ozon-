FROM python:3.11-slim
WORKDIR /app
# INSTALL_ML=false（默认）：只装 [dev]，镜像轻量，mock embedder 一键跑通；
# INSTALL_ML=true：额外装 [ml]（torch/cn_clip，体积达数 GB），供真实 CLIP 去重使用。
ARG INSTALL_ML=false
COPY pyproject.toml ./
RUN if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -e ".[dev,ml]"; else pip install --no-cache-dir -e ".[dev]"; fi
COPY . .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
