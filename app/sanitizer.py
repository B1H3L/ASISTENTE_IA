"""
sanitizer.py
Filtra datos sensibles antes de enviarlos a la IA y después de recibirlos.
Opera a nivel de columna (antes) y de texto (después).
"""

import re

# Nombres de columna que NUNCA se envían a la IA
BLOCKED_COLUMNS = {
    "password", "passwd", "pwd", "clave", "contrasena", "contrasenia",
    "token", "access_token", "refresh_token", "id_token",
    "api_key", "apikey", "secret", "client_secret", "app_secret",
    "private_key", "ssh_key", "rsa_key",
    "jwt", "bearer",
    "cookie", "session_id", "sessionid",
    "auth", "authorization",
    "connection_string", "db_url", "database_url",
    "webhook_secret", "signing_key",
    "credit_card", "tarjeta", "cvv", "pan",
    "ruc", "dni", "cedula", "nit",          # documentos personales
    "telefono", "celular", "movil", "phone",
    "correo", "email",
    "cloud_storage_endpoint_private",
    "cloud_storage_bucket_name",
    "fcm_token", "fcm_token_android", "fcm_token_ios",
    "mailserver_user", "mailserver_pass", "mailserver_password",
    "niubiz_key", "culqi_key", "kashio_key",
}

# Patrones en texto que se redactan en las respuestas de la IA
SENSITIVE_PATTERNS = [
    # API keys genéricas
    (re.compile(r'sk-[A-Za-z0-9\-_]{20,}', re.IGNORECASE), "[API_KEY_REDACTED]"),
    (re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}', re.IGNORECASE), "[API_KEY_REDACTED]"),
    # Tokens Bearer
    (re.compile(r'bearer\s+[A-Za-z0-9\-_\.]{20,}', re.IGNORECASE), "[BEARER_TOKEN_REDACTED]"),
    # JWT (tres segmentos base64 separados por punto)
    (re.compile(r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'), "[JWT_REDACTED]"),
    # Passwords en texto
    (re.compile(r'(password|passwd|clave|secret)\s*[:=]\s*\S+', re.IGNORECASE), "[CREDENTIAL_REDACTED]"),
    # API keys con prefijos comunes
    (re.compile(r'(api[_\-]?key|apikey)\s*[:=]\s*\S+', re.IGNORECASE), "[API_KEY_REDACTED]"),
    # URLs con credenciales embebidas (postgresql://user:pass@host)
    (re.compile(r'[a-z]+://[^:]+:[^@]+@', re.IGNORECASE), "[CONNECTION_STRING_REDACTED]@"),
    # Números de tarjeta (16 dígitos agrupados)
    (re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'), "[CARD_REDACTED]"),
    # Private keys PEM
    (re.compile(r'-----BEGIN [A-Z ]+KEY-----.*?-----END [A-Z ]+KEY-----', re.DOTALL), "[PRIVATE_KEY_REDACTED]"),
]


def sanitize_row(row: dict) -> dict:
    """
    Elimina columnas sensibles de una fila antes de enviarla a la IA.
    Compara en minúsculas para cubrir variantes de capitalización.
    """
    return {
        k: v
        for k, v in row.items()
        if k.lower() not in BLOCKED_COLUMNS
    }


def sanitize_context(context: list[dict]) -> list[dict]:
    """Aplica sanitize_row a cada entrada del contexto."""
    return [
        {"tabla": entry["tabla"], "datos": sanitize_row(entry["datos"])}
        for entry in context
    ]


def sanitize_response(text: str) -> str:
    """
    Redacta patrones sensibles en la respuesta de la IA.
    Si detecta una cantidad sospechosa de redacciones, cancela la respuesta.
    """
    redaction_count = 0
    for pattern, replacement in SENSITIVE_PATTERNS:
        new_text, n = pattern.subn(replacement, text)
        text = new_text
        redaction_count += n

    if redaction_count > 3:
        return "[RESPUESTA BLOQUEADA: contenía demasiada información sensible]"

    return text


# ─── DETECCIÓN DE VOLCADOS MASIVOS ───────────────────────────────────────────

def _is_response_dump(text: str) -> bool:
    """
    Heurísticas para detectar si la respuesta de la IA contiene un volcado masivo.

    Indicadores:
    - Muchas líneas con estructura de datos (pipes/comas como tabla o CSV)
    - Lista enumerada extremadamente larga
    - JSON arrays con múltiples objetos
    - Respuesta excesivamente larga con formato tabular
    """
    lines = [l for l in text.splitlines() if l.strip()]

    # Líneas con estructura de tabla/CSV (muchos separadores)
    data_lines = sum(1 for l in lines if l.count("|") > 2 or l.count(",") > 4)
    if data_lines > 150:
        return True

    # Demasiadas líneas totales (posible lista enumerada masiva sin control)
    if len(lines) > 500:
        return True

    # JSON con muchos objetos (volcado de registros)
    if text.count("},{") > 50 or text.count('"id":') > 50:
        return True

    # Patrones de lista numerada larga (1. ... 2. ... 15. ...)
    numbered = re.findall(r"^\s*\d+\.", text, re.MULTILINE)
    if len(numbered) > 50:
        return True

    return False


def post_filter_response(text: str) -> str:
    """
    Filtro final antes de enviar la respuesta al usuario.
    Solo redacta patrones sensibles (credenciales, tokens, etc.).
    La deteccion de volcados masivos ya no aplica aqui: el ACL y la
    allowlist de tablas garantizan que el contexto es legitimo, y los
    datos estructurados se devuelven directamente desde la DB en 'data'.
    """
    return sanitize_response(text)
