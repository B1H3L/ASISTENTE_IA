# Consultor IA

API REST que responde preguntas en lenguaje natural consultando una base de datos PostgreSQL y un modelo de IA (Claude / GPT).

---

## Instalación

```bash
git clone https://github.com/B1H3L/ASISTENTE_IA.git
cd consultor-ia
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copia el archivo de configuración y edítalo con tus datos:

```bash
copy app\.env.example app\.env
```

---

## Arranque

```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 8000
```

API disponible en `http://localhost:8000`.

En producción (con múltiples workers):

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Uso básico

```bash
# Verificar que el servidor está activo
curl http://localhost:8000/ping

# Hacer una consulta
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"cuantos alumnos hay?\", \"extra_params\": {\"api_key\": \"sk-ant-...\"}}"

# Estado de la DB
curl http://localhost:8000/health/db
```

---

## Logs

La API genera logs automáticamente en `logs/`:

- `logs/app.log` — arranque, queries, eventos generales
- `logs/security.log` — rate limit, prompt injection, bloqueos ACL

---

## Stack

- **FastAPI** — API REST
- **PostgreSQL** — base de datos
- **Claude / GPT** — modelos de IA (clave por request)
- **fpdf2** — generación de PDFs
