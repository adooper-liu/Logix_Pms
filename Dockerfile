FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖，利用镜像层缓存：只改代码时不会重新装包
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
COPY scripts ./scripts
# 迁移脚本必须一起进镜像：启动时会执行 alembic upgrade head
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8123

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8123/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8123"]
