from contextlib import asynccontextmanager
from fastapi import FastAPI
from db import check_connection
from routes.query import router as query_router
from security import SecurityMiddleware
from schema_loader import load_schema, load_foreign_keys
from query_cache import init_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa modulos que requieren DB al arrancar el servidor."""
    load_schema()        # Carga esquema de tablas permitidas en memoria
    load_foreign_keys()  # Descubre relaciones FK entre tablas permitidas
    init_cache()         # Crea tabla _ia_cache si no existe
    yield


app = FastAPI(title="Consultor IA API", version="0.1.0", lifespan=lifespan)

# Middleware de seguridad global (rate limiting + prompt injection)
app.add_middleware(SecurityMiddleware)

# Rutas
app.include_router(query_router, prefix="/api")


@app.get("/")
def root():
    """Endpoint raíz para confirmar que el servidor está activo."""
    return {"status": "ok", "message": "API corriendo correctamente"}


@app.get("/health/db")
def health_db():
    """Verifica que la conexión a PostgreSQL está disponible."""
    success, message = check_connection()
    if success:
        return {"status": "ok", "message": message}
    return {"status": "error", "message": message}


@app.post("/admin/cache/invalidate")
def admin_cache_invalidate():
    """Vacia el cache de respuestas (usar cuando cambie la DB o ALLOWED_TABLES)."""
    from query_cache import invalidate_cache
    deleted = invalidate_cache()
    return {"status": "ok", "deleted": deleted}


@app.post("/admin/schema/reload")
def admin_schema_reload():
    """Recarga el esquema de tablas desde la DB sin reiniciar el servidor."""
    from schema_loader import reload_schema, get_schema_text
    reload_schema()
    return {"status": "ok", "schema": get_schema_text()}
