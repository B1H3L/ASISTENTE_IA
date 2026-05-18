"""
security.py
Middleware de seguridad: rate limiting, prompt injection y bulk query detection.
"""

import re
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from acl import is_bulk_query, is_semantically_dangerous

# --- Rate limiting ---
# Máximo de peticiones por ventana de tiempo por IP
RATE_LIMIT_MAX = 30       # peticiones
RATE_LIMIT_WINDOW = 60    # segundos

_request_log: dict[str, list[float]] = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --- Prompt injection ---
# Patrones que intentan manipular al modelo para ignorar instrucciones
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+",
        r"act\s+as\s+(if\s+you\s+are\s+)?a",
        r"pretend\s+(you\s+are|to\s+be)",
        r"jailbreak",
        r"dan\s+mode",
        r"developer\s+mode",
        r"system\s+prompt",
        r"reveal\s+(your\s+)?(prompt|instructions|system)",
        r"print\s+(your\s+)?(prompt|instructions)",
        r"show\s+me\s+(your\s+)?(prompt|instructions|password|secret|key)",
        r"what\s+is\s+your\s+(api[_\s]?key|password|secret|token)",
        r"--\s*ignore",
        r"<\s*script",
        r"union\s+select",             # SQL injection en pregunta
        r"drop\s+table",
        r"insert\s+into",
        r"delete\s+from",
        r";\s*select",
    ]
]


def check_prompt_injection(text: str) -> bool:
    """Retorna True si detecta intento de prompt injection."""
    return any(p.search(text) for p in INJECTION_PATTERNS)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware global que aplica en cada request:
    1. Rate limiting por IP
    2. Detección de prompt injection en el body
    3. Detección de consultas masivas y acceso semántico peligroso
    """

    async def dispatch(self, request: Request, call_next):
        # 1. Rate limiting
        ip = _get_client_ip(request)
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW
        _request_log[ip] = [t for t in _request_log[ip] if t > window_start]

        if len(_request_log[ip]) >= RATE_LIMIT_MAX:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Demasiadas peticiones. Límite: {RATE_LIMIT_MAX} por {RATE_LIMIT_WINDOW}s."}
            )
        _request_log[ip].append(now)

        # 2. Inspección del body — solo en endpoints POST /api/
        if request.method == "POST" and request.url.path.startswith("/api/"):
            try:
                body = await request.body()
                text = body.decode("utf-8", errors="ignore")

                # 2a. Prompt injection
                if check_prompt_injection(text):
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: contiene patrones de inyección no permitidos."}
                    )

                # 2b. Consultas masivas de datos (segunda línea de defensa)
                if is_bulk_query(text):
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: consultas masivas de datos no están permitidas."}
                    )

                # 2c. Intención semántica peligrosa (segunda línea de defensa)
                if is_semantically_dangerous(text):
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: la solicitud intenta acceder a datos internos."}
                    )

                # Reconstruir el request con el body ya leído
                async def receive():
                    return {"type": "http.request", "body": body}
                request = Request(request.scope, receive)
            except Exception:
                pass  # Si no se puede leer el body, dejar pasar

        return await call_next(request)
