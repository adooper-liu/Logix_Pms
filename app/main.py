"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --reload
文档：
    http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 必须导入 models 以完成 ORM 注册，否则 Base.metadata 是空的
import app.models  # noqa: F401
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, ensure_postgres_extensions
from app.core.migrations import upgrade_head
from app.core.observe import AccessLogMiddleware, render_metrics
from app.core.security import using_dev_secret

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
SAMPLE_HTML = PROJECT_ROOT / "index-sample.html"
# 允许直接用 /orgs、/projects 这类路径打开前端；视图名与 web/js/main.js 的注册保持一致
SPA_VIEWS = {
    "workbench",
    "alignment",
    "start",
    "processes",
    "dashboard",
    "asset",
    "traceability",
    "strategy",
    "map",
    "process_card",
    "authorization",
    "pilot",
    "pcf",
    "bpmn",
    "cbok",
    "train",
    "workflow",
    "projects",
    "execution",
    "toolbox",
    "designer",
    "monitor",
    "data",
    "knowledge",
    "deliverables",
    "orgs",
    "sketches",
    "help",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if using_dev_secret() and not settings.allow_dev_secret:
        raise RuntimeError(
            "拒绝使用默认 SECRET_KEY 启动。生产环境请设置随机 SECRET_KEY；"
            "本地演示请在环境变量中设置 ALLOW_DEV_SECRET=true。"
        )
    # 生产走 Alembic；测试/临时环境可以关掉迁移、直接建表
    if settings.auto_migrate:
        upgrade_head()
    else:
        ensure_postgres_extensions()
        Base.metadata.create_all(bind=engine)

    # 演示账号只在显式允许开发密钥时灌入。生产即使误开 SEED_ON_STARTUP 也不会写入已知口令。
    if settings.seed_on_startup and settings.allow_dev_secret:
        from app.seed.fillable_templates import ensure_fillable_templates
        from app.seed.runner import seed_if_empty

        with SessionLocal() as db:
            seed_if_empty(db)
            ensure_fillable_templates(db)
            db.commit()
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "把 BPR、BPI、精益三大方法论整合为一套标准工作流：\n\n"
        "- **战略层**：流程架构（L1–L4）、流程 Owner、KPI 体系\n"
        "- **执行层**：识别 → 诊断 → 设计 → 落地 → 运营 五阶段标准工作流\n"
        "- **支撑层**：方法论工具箱、流程设计器、知识库\n"
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.allow_dev_secret else None,
    redoc_url="/redoc" if settings.allow_dev_secret else None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

# 前端静态资源（web/styles.css、web/app.js、web/views.js）
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/metrics", tags=["系统"], summary="进程内 HTTP 计数")
def metrics():
    return Response(render_metrics(), media_type="text/plain; version=0.0.4")


@app.get("/health", tags=["系统"], summary="健康检查")
def health():
    database_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False
    body = {
        "status": "ok" if database_ok else "error",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "database_ok": database_ok,
    }
    if not database_ok:
        return JSONResponse(body, status_code=503)
    return body


@app.get("/", include_in_schema=False)
def root():
    """前端主界面（已接后端 API）。"""
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        "<h1>前端未安装</h1><p>缺少 web/index.html。API 文档见 <a href='/docs'>/docs</a>。</p>",
        status_code=200,
    )


@app.get("/sample", include_in_schema=False)
def sample():
    """最初那份纯静态原型，保留作为设计对照。"""
    if SAMPLE_HTML.exists():
        return FileResponse(SAMPLE_HTML)
    return HTMLResponse("<p>未找到 index-sample.html。</p>", status_code=404)


@app.get("/{view_name}", include_in_schema=False)
def spa_view(view_name: str):
    """已知视图路径直接返回前端入口，前端启动后按路径/hash 选择视图。"""
    index = WEB_DIR / "index.html"
    if view_name in SPA_VIEWS and index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not Found")
