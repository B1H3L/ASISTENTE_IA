import os
from dotenv import load_dotenv

# Carga las variables desde el archivo .env
load_dotenv()

#print("CWD =", os.getcwd())
#print("ENV =", os.getenv("ANTHROPIC_API_KEY"))
# Configuración de la base de datos
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Tablas permitidas (separadas por coma en .env)
# Deben ser los nombres REALES de las tablas en la DB
ALLOWED_TABLES = {
    t.strip().lower()
    for t in os.getenv("ALLOWED_TABLES", "").split(",")
    if t.strip()
}

# Aliases de tablas: nombre_natural:nombre_real_en_db
# Permite que el usuario diga "alumno" y el sistema consulte "ist_alumno"
# Formato: TABLE_ALIASES=alumno:ist_alumno,persona:ist_persona
TABLE_ALIASES: dict[str, str] = {}
for _pair in os.getenv("TABLE_ALIASES", "").split(","):
    _pair = _pair.strip()
    if ":" in _pair:
        _logical, _real = _pair.split(":", 1)
        TABLE_ALIASES[_logical.strip().lower()] = _real.strip().lower()

# Descripciones de tablas en lenguaje natural.
# El sistema usa estas palabras para detectar que tabla consultar,
# sin importar como se llame la tabla en la DB.
# Formato: TABLE_DESCRIPTIONS=tabla_real:palabra1 palabra2 sinonimo;otra_tabla:palabra3
# Ejemplo: TABLE_DESCRIPTIONS=ist_alumno:alumno alumnos estudiante matriculado;ist_persona:persona nombre apellido
TABLE_DESCRIPTIONS: dict[str, set[str]] = {}  
for _entry in os.getenv("TABLE_DESCRIPTIONS", "").split(";"):
    _entry = _entry.strip()
    if ":" in _entry:
        _tbl, _desc = _entry.split(":", 1)
        _tbl = _tbl.strip().lower()
        if _tbl in ALLOWED_TABLES:
            TABLE_DESCRIPTIONS[_tbl] = {w.strip().lower() for w in _desc.split() if w.strip()}

# Proveedor por defecto: ollama | claude
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")

# Ollama (local)
AI_API_URL = os.getenv("AI_API_URL", "http://localhost:11434")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2:1b")

# Claude (Anthropic)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# GitHub Models (GPT-4o mini gratis)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_GPT_MODEL = os.getenv("GITHUB_GPT_MODEL", "gpt-4o-mini")

# Limite de tokens en la respuesta (aplica a todos los proveedores)
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "4096"))

# Cache de respuestas en PostgreSQL
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))
