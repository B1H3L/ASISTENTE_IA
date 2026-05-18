"""
acl.py — Access Control Layer

Política: DEFAULT DENY.
Todo lo no explícitamente permitido está bloqueado.

Jerarquía de seguridad:
  1. TABLE_DENYLIST  → bloqueo permanente, sin excepción
  2. ALLOWED_TABLES  → allowlist explícita (de config/.env)
  3. Todo lo demás   → bloqueado automáticamente
"""

import re
import config

# ─── DENYLIST DE TABLAS ───────────────────────────────────────────────────────
# La IA NUNCA puede leer, indexar, resumir ni inferir datos de estas tablas.
TABLE_DENYLIST: set[str] = {
    # Identidad corporativa y datos maestros de empresa
    "empresa", "empresas", "company", "companies",
    # Usuarios y autenticación
    "users", "user", "usuarios", "usuario",
    "admins", "admin", "administradores",
    "roles", "permissions", "permisos",
    "sessions", "session", "sesiones",
    "password_resets", "verification_tokens",
    "oauth_tokens", "oauth_clients",
    # Empleados y RRHH
    "employees", "employee", "empleados", "empleado",
    "staff", "personal",
    # Pagos y facturación
    "payments", "payment", "pagos", "pago",
    "billing", "facturas", "factura",
    "invoices", "invoice",
    "transactions", "transaction",
    # Claves y secretos
    "api_keys", "api_key", "apikeys",
    "secrets", "secret", "secretos",
    "tokens", "token",
    # Configuración interna
    "internal_config", "configuracion",
    "config", "settings",
    # Auditoría y logs
    "logs", "log", "audit_log", "audit_logs",
    "activity_log", "access_log",
    # Datos privados de clientes
    "customer_private_data", "private_data",
    "customers_sensitive",
    # Migraciones / meta
    "migrations", "schema_migrations",
    "django_migrations", "flyway_schema_history",
}

# ─── PATRONES: CONSULTA MASIVA DE DATOS ──────────────────────────────────────
# Detectan intención explícita de extraer grandes volúmenes o estructura de DB.
_BULK_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bselect\s+\*",                                          # SELECT *
        r"\btodos\s+los\s+(datos|registros|usuarios|campos|empleados|clientes)",
        r"\blista\s+(completa|total|entera|de\s+todos)",
        r"\bdame\s+todos\s+los\s+(datos|registros|usuarios|empleados|clientes|campos|tablas)\b",
        r"\bmuestra\s+(toda\s+la\s+tabla|todas\s+las\s+filas)",
        r"\bexporta?\s+(todo|toda|todos|la\s+base|el\s+backup|la\s+bd|los\s+datos)",
        r"\bdump\b",
        r"\bbackup\b",
        r"\braw\s+data\b",
        r"\btoda\s+la\s+tabla",
        r"\btodas\s+las\s+(filas|columnas|tablas|entradas)",
        r"\bdevuelve\s+todo",
        r"\bdevuelve\s+todas\s+las\s+filas",
        r"\bget\s+all\b",
        r"\bfetch\s+all\b",
        r"\blist\s+all\b",
        r"\bprint\s+(all|every|toda|todos)\b",
        r"\bextrae?\s+(todos|toda|el\s+contenido)",
    ]
]

# ─── PATRONES: PELIGRO SEMÁNTICO ─────────────────────────────────────────────
# Detectan reformulaciones peligrosas aunque no usen palabras clave obvias.
_SEMANTIC_DANGER_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bqu[eé]\s+contiene\s+(la\s+tabla|la\s+base|el\s+schema|la\s+bd)",
        r"\bqu[eé]\s+hay\s+en\s+(la\s+tabla|la\s+base|la\s+bd|el\s+schema)",
        r"\bimprime\s+(los\s+)?registros",
        r"\bmuestra\s+(los\s+)?registros\s+internos",
        r"\bdame\s+el\s+json\s+completo",
        r"\bexporta\s+la\s+base",
        r"\bdatos\s+completos\s+de\s+\w+",
        r"\binformaci[oó]n\s+completa\s+de\s+\w+",
        r"\btodos\s+los\s+campos\s+de",
        r"\bestructura\s+de\s+(la\s+)?tabla",
        r"\blistar\s+(todas\s+las\s+)?tablas",
        r"\bqu[eé]\s+tablas\s+(tienes|hay|existen|puedo\s+ver)",
        r"\bcu[aá]les\s+son\s+las\s+tablas",
        r"\baccede\s+a\s+la\s+tabla",
        r"\ble[eé]\s+la\s+tabla",
        r"\bconsulta\s+directa",
        r"\bquery\s+directo",
        r"\bdame\s+los\s+datos\s+(de\s+todos|completos)",
        r"\bmuestra\s+el\s+esquema",
        r"\bcu[aá]les\s+son\s+las\s+columnas",
        r"\bdescribe\s+(la\s+)?tabla",
        r"\binformaci[oó]n\s+interna",
        r"\bdatos\s+internos",
        r"\bregistros\s+internos",
    ]
]


def is_table_allowed(table_name: str) -> bool:
    """
    DEFAULT DENY: retorna True SOLO si la tabla está en ALLOWED_TABLES
    Y NO está en TABLE_DENYLIST.
    """
    name = table_name.lower().strip()
    if name in TABLE_DENYLIST:
        return False
    return name in config.ALLOWED_TABLES


def is_bulk_query(question: str) -> bool:
    """Detecta intención de extracción masiva de datos."""
    return any(p.search(question) for p in _BULK_PATTERNS)


def is_semantically_dangerous(question: str) -> bool:
    """Detecta intención peligrosa reformulada semánticamente."""
    return any(p.search(question) for p in _SEMANTIC_DANGER_PATTERNS)


def validate_question(question: str) -> tuple[bool, str]:
    """
    Validación integral de la pregunta ANTES de ejecutar cualquier búsqueda en DB.
    Aplica política DEFAULT DENY sobre intención.

    Retorna:
        (True, "")          → pregunta permitida
        (False, "motivo")   → pregunta bloqueada con motivo
    """
    if is_bulk_query(question):
        return False, "Consultas masivas de datos no están permitidas."
    if is_semantically_dangerous(question):
        return False, "La solicitud intenta acceder a datos internos o estructurales."
    return True, ""
