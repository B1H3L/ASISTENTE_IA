from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import check_connection
from routes.query import router as query_router
from security import SecurityMiddleware
from schema_loader import load_schema, load_foreign_keys
from query_cache import init_cache
import config
from logger import app_log


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_schema()
    load_foreign_keys()
    init_cache()
    app_log.info("API iniciada | proveedor=%s | tablas=%s", config.AI_PROVIDER, sorted(config.ALLOWED_TABLES))
    yield
    app_log.info("API detenida.")


app = FastAPI(title="Consultor IA API", version="0.1.0", lifespan=lifespan)

# cors
cors_origins = config.CORS_ORIGINS or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

app.add_middleware(SecurityMiddleware)
app.include_router(query_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "message": "API corriendo correctamente"}


@app.get("/ping")
def ping():
    from datetime import datetime
    return {
        "status": "ok",
        "message": "API corriendo",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/health/db")
def health_db():
    success, message = check_connection()
    if success:
        return {"status": "ok", "message": message}
    app_log.error("DB health check failed: %s", message)
    return {"status": "error", "message": "Error de conexión a la base de datos."}


@app.post("/admin/cache/invalidate")
def admin_cache_invalidate():
    from query_cache import invalidate_cache
    deleted = invalidate_cache()
    app_log.info("Cache invalidado: %d entradas.", deleted)
    return {"status": "ok", "deleted": deleted}


@app.post("/admin/schema/reload")
def admin_schema_reload():
    from schema_loader import reload_schema, get_schema_text
    reload_schema()
    app_log.info("Schema recargado.")
    return {"status": "ok", "schema": get_schema_text()}
