import re

# columnas que nunca se envían a la IA
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
    "ruc", "dni", "cedula", "nit",
    "telefono", "celular", "movil", "phone",
    "correo", "email",
    "cloud_storage_endpoint_private",
    "cloud_storage_bucket_name",
    "fcm_token", "fcm_token_android", "fcm_token_ios",
    "mailserver_user", "mailserver_pass", "mailserver_password",
    "niubiz_key", "culqi_key", "kashio_key",
}

# patrones sensibles a redactar en respuestas de la IA
SENSITIVE_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9\-_]{20,}', re.IGNORECASE), "[API_KEY_REDACTED]"),
    (re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}', re.IGNORECASE), "[API_KEY_REDACTED]"),
    (re.compile(r'bearer\s+[A-Za-z0-9\-_\.]{20,}', re.IGNORECASE), "[BEARER_TOKEN_REDACTED]"),
    (re.compile(r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'), "[JWT_REDACTED]"),
    (re.compile(r'(password|passwd|clave|secret)\s*[:=]\s*\S+', re.IGNORECASE), "[CREDENTIAL_REDACTED]"),
    (re.compile(r'(api[_\-]?key|apikey)\s*[:=]\s*\S+', re.IGNORECASE), "[API_KEY_REDACTED]"),
    (re.compile(r'[a-z]+://[^:]+:[^@]+@', re.IGNORECASE), "[CONNECTION_STRING_REDACTED]@"),
    (re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'), "[CARD_REDACTED]"),
    (re.compile(r'-----BEGIN [A-Z ]+KEY-----.*?-----END [A-Z ]+KEY-----', re.DOTALL), "[PRIVATE_KEY_REDACTED]"),
]


def sanitize_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if k.lower() not in BLOCKED_COLUMNS}


def sanitize_context(context: list[dict]) -> list[dict]:
    return [{"tabla": entry["tabla"], "datos": sanitize_row(entry["datos"])} for entry in context]


def sanitize_response(text: str) -> str:
    redaction_count = 0
    for pattern, replacement in SENSITIVE_PATTERNS:
        new_text, n = pattern.subn(replacement, text)
        text = new_text
        redaction_count += n
    if redaction_count > 3:
        return "[RESPUESTA BLOQUEADA: contenía demasiada información sensible]"
    return text


def _is_response_dump(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    data_lines = sum(1 for l in lines if l.count("|") > 2 or l.count(",") > 4)
    if data_lines > 150:
        return True
    if len(lines) > 500:
        return True
    if text.count("},{") > 50 or text.count('"id":') > 50:
        return True
    numbered = re.findall(r"^\s*\d+\.", text, re.MULTILINE)
    if len(numbered) > 50:
        return True
    return False


def post_filter_response(text: str) -> str:
    return sanitize_response(text)
