import os
from dotenv import load_dotenv

load_dotenv()

# base de datos
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# tablas permitidas
ALLOWED_TABLES = {
    t.strip().lower()
    for t in os.getenv("ALLOWED_TABLES", "").split(",")
    if t.strip()
}

# aliases nombre_natural -> nombre_real
TABLE_ALIASES: dict[str, str] = {}
for _pair in os.getenv("TABLE_ALIASES", "").split(","):
    _pair = _pair.strip()
    if ":" in _pair:
        _logical, _real = _pair.split(":", 1)
        TABLE_ALIASES[_logical.strip().lower()] = _real.strip().lower()

# palabras clave por tabla para detección semántica
TABLE_DESCRIPTIONS: dict[str, set[str]] = {}
for _entry in os.getenv("TABLE_DESCRIPTIONS", "").split(";"):
    _entry = _entry.strip()
    if ":" in _entry:
        _tbl, _desc = _entry.split(":", 1)
        _tbl = _tbl.strip().lower()
        if _tbl in ALLOWED_TABLES:
            TABLE_DESCRIPTIONS[_tbl] = {w.strip().lower() for w in _desc.split() if w.strip()}

# proveedor de IA
AI_PROVIDER = os.getenv("AI_PROVIDER", "claude")

# claude
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# github/gpt
GITHUB_GPT_MODEL = os.getenv("GITHUB_GPT_MODEL", "gpt-4o-mini")

# límite de tokens
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "4096"))

# cache
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))

# rate limiting
TRUST_PROXY: bool = os.getenv("TRUST_PROXY", "false").lower() == "true"
RATE_LIMIT_MAX_IPS: int = int(os.getenv("RATE_LIMIT_MAX_IPS", "10000"))

# límites de entrada
MAX_QUESTION_LENGTH: int = int(os.getenv("MAX_QUESTION_LENGTH", "2000"))
MAX_BODY_SIZE: int = int(os.getenv("MAX_BODY_SIZE", str(1 * 1024 * 1024)))

# cors
CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
