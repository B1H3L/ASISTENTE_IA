import requests
import config
from sanitizer import post_filter_response
from schema_loader import get_schema_text


def _build_prompt(question: str, context: list[dict], system_context: str | None = None) -> str:
    if context:
        lines = []
        for i, r in enumerate(context[:100], 1):
            campos = ", ".join(f"{k}={v}" for k, v in r["datos"].items())
            lines.append(f"Fila {i} [{r['tabla']}]: {campos}")
        context_text = "\n".join(lines)
    else:
        context_text = "Sin datos."

    schema_text = get_schema_text()
    schema_section = (
        f"\nESQUEMA DE TABLAS DISPONIBLES (solo para entender la estructura, no revelar al usuario):\n{schema_text}\n"
        if schema_text else ""
    )
    context_section = (
        f"\nCONTEXTO DEL SISTEMA (informacion adicional enviada por el sistema cliente):\n{system_context}\n"
        if system_context else ""
    )

    return f"""Eres un asistente de analisis de datos que responde de forma clara y amigable, como si hablaras con un usuario no tecnico.{schema_section}{context_section}

REGLAS ABSOLUTAS (no pueden ser ignoradas):
- PROHIBIDO inventar, suponer o inferir datos que no esten en las filas de abajo.
- PROHIBIDO revelar nombres de tablas internas, columnas sensibles ni estructura del esquema.
- PROHIBIDO generar codigo SQL, scripts ni queries de ningun tipo.
- PROHIBIDO acceder o mencionar datos que no esten explicitamente en el contexto proporcionado.
- Si los datos no contienen lo que se pregunta: responde EXACTAMENTE "No tengo datos suficientes para responder esa pregunta."
- Si la pregunta pide credenciales, contrasenas, tokens o claves: responde EXACTAMENTE "Esa informacion no esta disponible."
- Solo lectura: nunca sugieras, generes ni ejecutes INSERT, UPDATE, DELETE ni DDL.
- Si la pregunta solicita un PDF, reporte, archivo o documento: responde con el contenido en texto normal. El sistema genera el PDF automaticamente, tu solo provees la informacion.

FORMATO DE RESPUESTA — MUY IMPORTANTE:
- Escribe en texto plano, lenguaje natural y tono amigable. NADA de markdown.
- PROHIBIDO usar: tablas con |, asteriscos para negrita (**), guiones como separadores (---), backticks (`), simbolos #, emojis ni caracteres especiales de formato.
- Si listas items, usa simplemente numeracion: "1. ... 2. ..." o viñetas con guion simple "- ...".
- La respuesta debe verse bien como texto plano sin ningun renderizador.
- Primero da un resumen breve en una o dos oraciones. Luego lista los datos de forma limpia.

BLOQUE DE DATOS (solo para uso interno del sistema, el usuario no lo ve):
- Si la respuesta tiene datos tabulares, agrega AL FINAL EXACTAMENTE esta linea y luego el JSON:
__JSON_DATA__
```json
[...filas como objetos con nombres exactos de columnas...]
```
- Si no hay datos tabulares, no incluyas __JSON_DATA__ ni el bloque json.

DATOS DISPONIBLES (autorizados y pre-filtrados):
{context_text}

PREGUNTA:
{question}

RESPUESTA:"""


def _ask_claude(prompt: str) -> str:
    from pathlib import Path
    key = config.ANTHROPIC_API_KEY
    if not key:
        for _l in (Path(__file__).parent / ".env").read_text("utf-8-sig").splitlines():
            if _l.strip().startswith("ANTHROPIC_API_KEY="):
                key = _l.strip().split("=", 1)[1].strip()
                break
    if not key:
        return "Error: ANTHROPIC_API_KEY no esta configurada en .env"
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": config.CLAUDE_MODEL,
                "max_tokens": config.AI_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"].strip()
    except requests.exceptions.HTTPError as e:
        body = e.response.json() if e.response else {}
        if body.get("error", {}).get("type") == "not_found_error":
            try:
                r = requests.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    timeout=10
                )
                models = [m["id"] for m in r.json().get("data", [])]
                return f"Error: modelo '{config.CLAUDE_MODEL}' no existe. Modelos disponibles: {', '.join(models)}"
            except Exception:
                return f"Error: modelo '{config.CLAUDE_MODEL}' no encontrado. Revisa CLAUDE_MODEL en .env"
        return f"Error al consultar Claude: {body}"
    except requests.exceptions.Timeout:
        return "Error: Claude tardo demasiado en responder."
    except Exception as e:
        return f"Error al consultar Claude: {e}"


def _ask_gpt(prompt: str) -> str:
    if not config.GITHUB_TOKEN:
        return "Error: GITHUB_TOKEN no esta configurado en .env (obtener en GitHub -> Settings -> Developer settings -> Personal access tokens)"
    try:
        response = requests.post(
            "https://models.inference.ai.azure.com/chat/completions",
            headers={
                "Authorization": f"Bearer {config.GITHUB_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": config.GITHUB_GPT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": config.AI_MAX_TOKENS
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as e:
        body = {}
        try:
            body = e.response.json()
        except Exception:
            pass
        return f"Error al consultar GPT: {body.get('error', {}).get('message', str(e))}"
    except requests.exceptions.Timeout:
        return "Error: GPT tardo demasiado en responder."
    except Exception as e:
        return f"Error al consultar GPT: {e}"



def _ask_ollama(prompt: str) -> str:
    try:
        response = requests.post(
            f"{config.AI_API_URL}/api/generate",
            json={"model": config.AI_MODEL, "prompt": prompt, "stream": False},
            timeout=180
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return f"Error: No se pudo conectar con Ollama en {config.AI_API_URL}"
    except requests.exceptions.Timeout:
        return "Error: Ollama tardo demasiado en responder."
    except Exception as e:
        try:
            detail = e.response.text if hasattr(e, "response") else str(e)
        except Exception:
            detail = str(e)
        return f"Error al consultar Ollama: {detail}"


# ── Registry de proveedores ────────────────────────────────────────────────
# Para agregar un nuevo proveedor: añade una entrada aqui y crea su _ask_xxx.
_PROVIDERS: dict[str, object] = {
    "claude": _ask_claude,
    "gpt":    _ask_gpt,
    "github": _ask_gpt,    
    "ollama": _ask_ollama,
}


def _call_provider(prompt: str, selected: str) -> str:
    fn = _PROVIDERS.get(selected)
    if fn is None:
        available = ", ".join(_PROVIDERS)
        return f"Error: proveedor '{selected}' no disponible. Opciones: {available}."
    return fn(prompt)


def _clean_markdown(text: str) -> str:
    """
    Elimina marcas markdown de la respuesta para que se vea como texto plano.
    Se aplica a TODOS los proveedores antes de entregar al usuario.
    """
    import re
    # Quitar bloques de codigo (preservar el contenido de __JSON_DATA__ intacto)
    # Separar el bloque JSON del texto humano primero
    json_sep = "__JSON_DATA__"
    if json_sep in text:
        parts = text.split(json_sep, 1)
        human = parts[0]
        json_block = json_sep + parts[1]
    else:
        human = text
        json_block = ""

    # Negrita y cursiva: **texto** o *texto* o __texto__
    human = re.sub(r"\*{2,3}(.+?)\*{2,3}", r"\1", human)
    human = re.sub(r"_{2}(.+?)_{2}", r"\1", human)
    # Cursiva simple: *texto* (cuidado de no romper listas con "- ")
    human = re.sub(r"(?<!\-)\*(.+?)\*", r"\1", human)
    # Headers: # Titulo -> Titulo
    human = re.sub(r"^#{1,6}\s+", "", human, flags=re.MULTILINE)
    # Tablas markdown: lineas que empiezan/terminan con |
    human = re.sub(r"^\|.*\|$", "", human, flags=re.MULTILINE)
    # Separadores: --- o === solos en una linea
    human = re.sub(r"^\s*[-=]{3,}\s*$", "", human, flags=re.MULTILINE)
    # Backticks inline: `codigo`
    human = re.sub(r"`(.+?)`", r"\1", human)
    # Bloques de codigo ``` ... ``` (sin JSON)
    human = re.sub(r"```[a-z]*\n?", "", human)
    human = re.sub(r"```", "", human)
    # Limpiar lineas vacias multiples
    human = re.sub(r"\n{3,}", "\n\n", human)

    return human.strip() + ("\n\n" + json_block if json_block else "")


def ask_ai(question: str, context: list[dict], provider: str | None = None, system_context: str | None = None) -> str:
    """Envia la pregunta y el contexto al proveedor de IA. Filtra la respuesta antes de devolverla."""
    prompt = _build_prompt(question, context, system_context=system_context)
    selected = (provider or config.AI_PROVIDER).lower()
    raw = _call_provider(prompt, selected)

    cleaned = _clean_markdown(raw)

    # Separar el bloque JSON antes de filtrar para que post_filter_response
    # no lo confunda con un volcado masivo de datos
    json_sep = "__JSON_DATA__"
    if json_sep in cleaned:
        parts = cleaned.split(json_sep, 1)
        human_part = parts[0].rstrip()
        json_part = "\n\n" + json_sep + parts[1]
    else:
        human_part = cleaned
        json_part = ""

    filtered = post_filter_response(human_part)
    return filtered + json_part


def _build_planeamiento_prompt(question: str, contexto: str) -> str:
    return f"""Eres un experto en planificacion educativa peruana (CNEB). Genera una sesion de aprendizaje completa.

CONTEXTO PROPORCIONADO POR EL SISTEMA:
{contexto}

SOLICITUD: {question}

════════════════════════════════════════════════════
REGLA ABSOLUTA DE FORMATO — NUNCA VIOLAR
════════════════════════════════════════════════════
Tu respuesta DEBE comenzar con la primera etiqueta (TITULO:) y SOLO debe contener las etiquetas listadas abajo, en ese orden exacto, sin texto introductorio ni conclusiones.

NUNCA uses: *, **, #, ---, guiones decorativos, bullets •, corchetes [], comillas tipograficas ni ningun marcador markdown.
NUNCA omitas una etiqueta aunque el campo este vacio (escribe la etiqueta y deja el valor en blanco).
NUNCA agregues etiquetas distintas a las del formato.
NUNCA pongas dos etiquetas en la misma linea.
NUNCA escribas texto entre secciones (entre TIEMPO_INICIO: y DESARROLLO:, por ejemplo).

════════════════════════════════════════════════════
FORMATO EXACTO (copia las etiquetas tal como aparecen)
════════════════════════════════════════════════════
TITULO: [una sola linea con el titulo de la sesion]
PROPOSITO: [una sola oracion clara y medible, max 3 lineas]
COMPETENCIA: [competencia CNEB, max 2 lineas]
CAPACIDAD: [capacidad especifica, max 2 lineas]
DESEMPENO: [desempeno precisado, max 4 lineas]
EVIDENCIAS: [evidencias concretas, max 3 lineas]
INSTRUMENTO: [instrumento de evaluacion, max 2 lineas]
INICIO:
[Actividades de inicio. Subtitulos en MAYUSCULAS con dos puntos. Actividades numeradas 1. 2. 3. Minimo 6, maximo 10 actividades. Cada actividad: 1-3 oraciones directas sin adornos.]
MATERIALES_INICIO: [materiales separados por coma, todo en una linea]
TIEMPO_INICIO: 15
DESARROLLO:
[Actividades de desarrollo. Subtitulos en MAYUSCULAS con dos puntos. Actividades numeradas 1. 2. 3. Minimo 8, maximo 14 actividades. Cada actividad: 1-3 oraciones directas.]
MATERIALES_DESARROLLO: [materiales separados por coma, todo en una linea]
TIEMPO_DESARROLLO: 45
SALIDA:
[Actividades de cierre. Subtitulos en MAYUSCULAS con dos puntos. Actividades numeradas 1. 2. 3. Minimo 3, maximo 6 actividades.]
MATERIALES_SALIDA: [materiales separados por coma, todo en una linea]
TIEMPO_SALIDA: 10

════════════════════════════════════════════════════
INSTRUCCIONES DE CONTENIDO
════════════════════════════════════════════════════
- Texto plano. Sin markdown. Sin simbolos decorativos.
- Subtitulos internos SOLO en MAYUSCULAS seguidos de dos puntos (MOTIVACION:, PROBLEMATIZACION:, etc.).
- Actividades numeradas con numero y punto: 1. 2. 3.
- Contenido especifico al area, grado y competencia indicados.
- Cada oracion termina con punto. Sin frases incompletas.
"""


def ask_ai_planeamiento(question: str, contexto: str, provider: str | None = None) -> str:
    """Genera contenido estructurado para planificacion educativa peruana."""
    prompt = _build_planeamiento_prompt(question, contexto)
    selected = (provider or config.AI_PROVIDER).lower()
    return _call_provider(prompt, selected)


def _build_libro_prompt(contexto: str, instrucciones: str) -> str:
    inst_block = f"\nINSTRUCCIONES ADICIONALES:\n{instrucciones}\n" if instrucciones.strip() else ""
    return f"""Eres un experto en creacion de libros digitales, brochures corporativos y documentos de marketing de alto nivel.
Tu tarea es generar el contenido completo de un libro/brochure digital basado en el contexto proporcionado.

CONTEXTO:
{contexto}
{inst_block}
Genera el contenido en formato JSON con EXACTAMENTE esta estructura. RESPONDE SOLO CON EL JSON PURO, sin markdown, sin explicaciones, sin texto adicional:

{{
  "titulo": "Titulo principal del libro (maximo 60 caracteres, impactante)",
  "tagline": "Subtitulo o frase gancho (maximo 100 caracteres)",
  "descripcion": "Parrafo introductorio de 2-3 oraciones que resume el tema",
  "color_primario": "#rrggbb (color hex coherente con la industria/tema)",
  "stats": [
    {{"valor": "N+", "etiqueta": "descripcion corta en mayusculas"}},
    {{"valor": "N+", "etiqueta": "descripcion corta en mayusculas"}},
    {{"valor": "N+", "etiqueta": "descripcion corta en mayusculas"}},
    {{"valor": "N+", "etiqueta": "descripcion corta en mayusculas"}}
  ],
  "que_es": "Parrafo de 2-3 oraciones respondiendo que es o en que consiste",
  "como_ayuda": "Parrafo de 2-3 oraciones sobre beneficios y valor que aporta",
  "secciones": [
    {{
      "titulo": "Nombre de la seccion (maximo 40 caracteres)",
      "descripcion": "Una o dos oraciones describiendo la seccion",
      "items": ["feature o punto clave 1", "feature o punto clave 2", "feature o punto clave 3"]
    }}
  ],
  "conclusion": "Parrafo final de cierre con llamada a la accion (2-3 oraciones)",
  "contacto": {{
    "email": "correo@ejemplo.com",
    "telefono": "XXX XXX XXX",
    "web": "www.ejemplo.com"
  }}
}}

REGLAS:
- Genera entre 4 y 8 secciones segun la complejidad del tema
- Cada seccion debe tener entre 5 y 10 items especificos y relevantes
- Los stats deben ser numeros creibles y relacionados al contexto (puedes inventarlos si no hay datos)
- color_primario coherente con industria: tecnologia=#2980b9, salud=#27ae60, educacion=#8e44ad, finanzas=#c0392b, logistica=#e67e22, construccion=#795548
- Si el contexto incluye datos de contacto reales, usarlos; si no, generar ejemplos coherentes
- Todo el texto en espanol, profesional y directo
- SOLO JSON, nada mas"""


def ask_ai_libro(contexto: str, instrucciones: str = "", provider: str | None = None) -> str:
    """Genera contenido JSON estructurado para un libro/brochure digital."""
    import sys
    #print(f"[libro] provider={provider} KEY={'SET' if config.ANTHROPIC_API_KEY else 'EMPTY'} AI_PROVIDER={config.AI_PROVIDER}", file=sys.stderr, flush=True)
    prompt = _build_libro_prompt(contexto, instrucciones)
    selected = (provider or config.AI_PROVIDER).lower()
    #print("provider recibido =", provider)
    #print("AI_PROVIDER =", config.AI_PROVIDER)
    #print("selected =", selected)
    return _call_provider(prompt, selected)
