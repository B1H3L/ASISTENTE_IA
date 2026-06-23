import re
import json
import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from acl import is_bulk_query, is_semantically_dangerous
import config
from logger import security_log

RATE_LIMIT_MAX = 30
RATE_LIMIT_WINDOW = 60

_request_log: dict[str, list[float]] = defaultdict(list)

# headers de seguridad HTTP
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'",
}

# patrones de prompt injection
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
        r"union\s+select",
        r"drop\s+table",
        r"insert\s+into",
        r"delete\s+from",
        r";\s*select",
    ]
]


def check_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def _get_client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _safe_log_body(text: str) -> str:
    try:
        parsed = json.loads(text)
        parsed.pop("api_key", None)
        if isinstance(parsed.get("extra_params"), dict):
            parsed["extra_params"].pop("api_key", None)
        return json.dumps(parsed, ensure_ascii=False)[:400]
    except Exception:
        return text[:400]


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = _get_client_ip(request)
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW

        # rate limiting con cap de memoria
        _request_log[ip] = [t for t in _request_log[ip] if t > window_start]
        if len(_request_log) > config.RATE_LIMIT_MAX_IPS:
            expired = [k for k, v in list(_request_log.items()) if not v]
            for k in expired:
                del _request_log[k]

        if len(_request_log[ip]) >= RATE_LIMIT_MAX:
            security_log.warning("RATE_LIMIT | ip=%s | path=%s", ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": f"Demasiadas peticiones. Límite: {RATE_LIMIT_MAX} por {RATE_LIMIT_WINDOW}s."}
            )
        _request_log[ip].append(now)

        # límite de tamaño de body
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > config.MAX_BODY_SIZE:
                    security_log.warning("BODY_TOO_LARGE | ip=%s | size=%s", ip, content_length)
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Request demasiado grande. Máximo: {config.MAX_BODY_SIZE // 1024} KB."}
                    )
            except ValueError:
                pass

        # inspección del body
        if request.method == "POST" and request.url.path.startswith("/api/"):
            try:
                body = await request.body()
                text = body.decode("utf-8", errors="ignore")

                if check_prompt_injection(text):
                    security_log.warning("PROMPT_INJECTION | ip=%s | body=%s", ip, _safe_log_body(text))
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: contiene patrones de inyección no permitidos."}
                    )

                if is_bulk_query(text):
                    security_log.warning("BULK_QUERY | ip=%s | body=%s", ip, _safe_log_body(text))
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: consultas masivas de datos no están permitidas."}
                    )

                if is_semantically_dangerous(text):
                    security_log.warning("SEMANTIC_DANGER | ip=%s | body=%s", ip, _safe_log_body(text))
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Solicitud bloqueada: la solicitud intenta acceder a datos internos."}
                    )

                async def receive():
                    return {"type": "http.request", "body": body}
                request = Request(request.scope, receive)

            except Exception as exc:
                security_log.error("MIDDLEWARE_ERROR | ip=%s | error=%s", ip, exc)
                return JSONResponse(status_code=400, content={"detail": "No se pudo procesar el request."})

        response: Response = await call_next(request)

        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
