# Instalación

## Requisitos del sistema

| Requisito | Versión mínima |
|---|---|
| Python | 3.10+ |
| pip | 22+ |
| PostgreSQL | 13+ |
| RAM | 512 MB recomendado |
| SO | Windows |

---

## 1. Clonar el repositorio

```powershell
git clone https://github.com/B1H3L/ASISTENTE_IA.git
cd ASISTENTE_IA
```

---

## 2. Instalar dependencias

=== "Windows"

    ```powershell
    pip install -r requirements.txt
    ```

=== "Linux"

    ```bash
    pip3 install -r requirements.txt
    ```

| Paquete | Uso |
|---|---|
| `fastapi` | Framework web y API REST |
| `uvicorn` | Servidor ASGI |
| `psycopg2-binary` | Conexión a PostgreSQL |
| `python-dotenv` | Leer variables del `.env` |
| `requests` | Llamadas HTTP a los proveedores de IA |
| `fpdf2` | Generación de PDFs |

---

## 4. Configurar el entorno

Copia el archivo de ejemplo y edítalo con tus datos:

```powershell
copy app\.env.example app\.env
```

Abre `app\.env` y completa como mínimo:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nombre_de_tu_base
DB_USER=tu_usuario
DB_PASSWORD=tu_password

ALLOWED_TABLES=tabla1,tabla2
```

El resto de variables tiene valores por defecto y no es obligatorio cambiarlos para arrancar.

---

## 5. Iniciar la API

=== "Windows"

    ```powershell
    cd app
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```

=== "Linux"

    ```bash
    cd app
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```

    En producción con múltiples workers:

    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
    ```

API disponible en `http://localhost:8000`.

---

## Verificar la instalación

```powershell
curl http://localhost:8000/ping
```

Respuesta esperada:

```json
{
  "status": "ok",
  "message": "API corriendo",
  "time": "2026-06-23 15:00:00"
}
```

---

## Estructura de carpetas tras la instalación

```
ASISTENTE_IA/
├── app/
│   ├── main.py
│   ├── .env              ← creado por ti (no se sube al repo)
│   └── ...
├── logs/
│   ├── app.log           ← generado automáticamente
│   └── security.log      ← generado automáticamente
├── docs/
│   └── instalacion.md
└── requirements.txt
```

---

## Logs del servidor

La API genera logs en `logs/` automáticamente al iniciarse.

| Archivo | Contenido |
|---|---|
| `app.log` | Arranque, queries, eventos generales |
| `security.log` | Rate limit, prompt injection, bloqueos ACL |

Cada archivo rota al llegar a **10 MB** y conserva hasta **5 archivos** anteriores.

---

## Actualizar el servidor tras cambios

### 1. Descargar los cambios

```powershell
cd ASISTENTE_IA
git pull origin master
```

### 2. Instalar nuevas dependencias (si las hay)

=== "Windows"

    ```powershell
    pip install -r requirements.txt
    ```

=== "Linux"

    ```bash
    pip3 install -r requirements.txt
    ```

### 3. Reiniciar el servidor

=== "Windows"

    Detén el proceso con `Ctrl+C` y vuelve a iniciarlo:

    ```powershell
    cd app
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```

=== "Linux"

    ```bash
    pkill -f "uvicorn"
    cd app
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 &> ../logs/uvicorn.log &
    ```

### 4. Confirmar que el servidor está activo

```powershell
curl http://localhost:8000/ping
```

### 5. Revisar el log tras el reinicio

```powershell
Get-Content logs\app.log -Tail 20
```
