"""
Cache de respuestas en PostgreSQL.
Guarda preguntas + respuestas para evitar repetir consultas a la DB y al proveedor de IA.
La tabla _ia_cache se crea automaticamente si no existe.
Es agnóstico al proveedor: guarda qué proveedor respondio, pero funciona con cualquiera.
"""
import hashlib
from datetime import datetime, timedelta
import config
from db import get_connection


def _normalize(question: str) -> str:
    """Normaliza la pregunta: minusculas, sin espacios dobles."""
    return " ".join(question.lower().strip().split())


def _hash(question: str) -> str:
    """SHA-256 de la pregunta normalizada para busqueda rapida por indice."""
    return hashlib.sha256(_normalize(question).encode()).hexdigest()


def init_cache() -> None:
    """
    Crea la tabla _ia_cache e indice si no existen.
    Llama a esta funcion una vez al iniciar el servidor (en main.py).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _ia_cache (
                id          SERIAL PRIMARY KEY,
                question_hash VARCHAR(64) NOT NULL,
                question    TEXT NOT NULL,
                answer      TEXT NOT NULL,
                context_count INTEGER DEFAULT 0,
                provider    VARCHAR(50) DEFAULT '',
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_ia_cache_hash ON _ia_cache(question_hash)"
        )
        conn.commit()
        cur.close()
        conn.close()
        print("[query_cache] Tabla _ia_cache lista.")
    except Exception as e:
        print(f"[query_cache] Advertencia: no se pudo inicializar cache: {e}")


def get_cached_response(question: str) -> dict | None:
    """
    Busca una respuesta cacheada valida (dentro del TTL).
    Devuelve dict {answer, context_count, provider} o None si no hay hit.
    """
    if not config.CACHE_ENABLED:
        return None
    try:
        cutoff = datetime.now() - timedelta(hours=config.CACHE_TTL_HOURS)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT answer, context_count, provider
            FROM _ia_cache
            WHERE question_hash = %s
              AND created_at > %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (_hash(question), cutoff),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"answer": row[0], "context_count": row[1], "provider": row[2]}
    except Exception:
        pass
    return None


def save_to_cache(
    question: str, answer: str, context_count: int, provider: str = ""
) -> None:
    """Guarda la respuesta en cache. Falla silenciosamente para no interrumpir al usuario."""
    if not config.CACHE_ENABLED:
        return
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO _ia_cache (question_hash, question, answer, context_count, provider)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (_hash(question), _normalize(question), answer, context_count, provider),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def invalidate_cache() -> int:
    """
    Elimina todas las entradas del cache.
    Util si se cambian ALLOWED_TABLES o se actualiza la DB.
    Devuelve cuantas filas fueron eliminadas.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM _ia_cache")
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return deleted
    except Exception:
        return 0
