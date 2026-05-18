from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal
from fpdf import FPDF
from searcher import search_relevant_data, ACCESS_DENIED
from ai_client import ask_ai
from acl import validate_question
from query_cache import get_cached_response, save_to_cache

router = APIRouter()

PDF_KEYWORDS = {"pdf", "archivo", "descarga", "documento", "reporte", "informe", "exportar"}


class QueryRequest(BaseModel):
    question: str
    provider: Literal["ollama", "claude", "gpt", "github"] | None = None
    extra_params: dict | None = None
    # extra_params acepta cualquier clave que el sistema cliente quiera enviar.
    # Claves reconocidas:
    #   "tablas": list[str]  -> tablas a consultar en este request (deben estar en ALLOWED_TABLES)
    #   "contexto": str      -> contexto libre que la IA recibe en el prompt


class QueryResponse(BaseModel):
    question: str
    context_found: int
    answer: str
    data: list[dict] | None = None  
    provider_used: str


def _wants_pdf(question: str) -> bool:
    words = {w.strip("¿?.,;:").lower() for w in question.split()}
    return bool(words & PDF_KEYWORDS)


def _sanitize(text: str) -> str:
    """Elimina caracteres fuera del rango latin-1 (emojis, símbolos Unicode, etc.)"""
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _extract_json_block(content: str) -> tuple[list[dict], str]:
    """
    Extrae el bloque ---DATOS_JSON--- del final de la respuesta de la IA.
    Devuelve (filas, texto_limpio_para_usuario).
    """
    import re, json
    # Separador explícito que pone el prompt
    if "__JSON_DATA__" in content:
        parts = content.split("__JSON_DATA__", 1)
        human_text = parts[0].rstrip()
        raw_json = parts[1]
    elif "---DATOS_JSON---" in content:
        # compatibilidad con respuestas antiguas
        parts = content.split("---DATOS_JSON---", 1)
        human_text = parts[0].rstrip()
        raw_json = parts[1]
    else:
        # Fallback: bloque ```json [...] ``` al final
        m = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)
        if not m:
            return [], content
        human_text = content[:m.start()].rstrip()
        raw_json = m.group(1)

    # Extraer el array JSON del bloque
    m2 = re.search(r"(\[.*?\])", raw_json, re.DOTALL)
    if not m2:
        return [], human_text
    try:
        rows = json.loads(m2.group(1))
        if isinstance(rows, list) and rows:
            return rows, human_text
    except Exception:
        pass
    return [], human_text
    """Quita marcas markdown: negrita, cursiva, backticks."""
    import re
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def _build_pdf(title: str, content: str) -> bytes:
    from datetime import date

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    # ── Cabecera azul ────────────────────────────────────────────
    pdf.set_fill_color(28, 78, 148)
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_y(5)
    pdf.set_font("Helvetica", style="B", size=15)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, _sanitize("Consultor IA  |  Reporte de Datos"), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 6, _sanitize(f"Generado el {date.today().strftime('%d/%m/%Y')}"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # ── Título / pregunta ────────────────────────────────────────
    pdf.set_fill_color(232, 240, 255)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.multi_cell(0, 8, _sanitize(title[:150]), fill=True,
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── Extraer bloque JSON si la IA lo incluyó ─────────────────
    json_rows, content = _extract_json_block(content)

    # ── Clasificar líneas del contenido ─────────────────────────
    pipe_rows:  list[list[str]] = []   # tabla markdown con |
    equal_rows: list[tuple[str, str]] = []  # KEY = VALUE
    prose_lines: list[str] = []

    for raw_line in content.splitlines():
        line = _strip_md(raw_line).strip().lstrip("-").strip()
        if not line:
            continue
        # Separador markdown |--- o |===
        if set(line.replace("|", "").replace("-", "").replace("=", "").strip()) == set():
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts:
                pipe_rows.append(parts)
            continue
        if "=" in line:
            parts = line.split("=", 1)
            k, v = parts[0].strip(), parts[1].strip()
            if k and v:
                equal_rows.append((k, v))
                continue
        prose_lines.append(line)

    def _table_header(cols: list[str], widths: list[int]):
        pdf.set_fill_color(28, 78, 148)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", style="B", size=9)
        for col, w in zip(cols, widths):
            pdf.cell(w, 8, _sanitize(col[:40]), fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=9)

    def _table_rows_pipe(rows: list[list[str]], header: list[str], widths: list[int]):
        alternado = False
        for row in rows:
            if pdf.get_y() > 262:
                pdf.add_page()
                _table_header(header, widths)
            pdf.set_fill_color(233, 241, 255) if alternado else pdf.set_fill_color(248, 250, 255)
            for i, w in enumerate(widths):
                val = row[i] if i < len(row) else ""
                pdf.cell(w, 7, _sanitize(val[:55]), fill=True)
            pdf.ln()
            alternado = not alternado
        pdf.ln(4)

    # ── Renderizar tabla desde bloque JSON (columnas exactas) ────
    if json_rows:
        columns = list(json_rows[0].keys())
        total_w = 180
        col_w = max(20, total_w // len(columns))
        widths = [col_w] * len(columns)
        _table_header([c.upper() for c in columns], widths)
        alternado = False
        for row in json_rows:
            if pdf.get_y() > 262:
                pdf.add_page()
                _table_header([c.upper() for c in columns], widths)
            pdf.set_fill_color(233, 241, 255) if alternado else pdf.set_fill_color(248, 250, 255)
            for col, w in zip(columns, widths):
                val = str(row.get(col, ""))
                pdf.cell(w, 7, _sanitize(val[:40]), fill=True)
            pdf.ln()
            alternado = not alternado
        pdf.ln(4)

    # ── Renderizar tabla markdown con | ──────────────────────────
    if pipe_rows:
        header = pipe_rows[0]
        data   = pipe_rows[1:]
        ncols  = len(header)
        col_w  = 180 // ncols
        widths = [col_w] * ncols
        _table_header(header, widths)
        _table_rows_pipe(data, header, widths)

    # ── Renderizar tabla KEY = VALUE ─────────────────────────────
    if equal_rows:
        _table_header(["CAMPO", "VALOR"], [75, 105])
        alternado = False
        for k, v in equal_rows:
            if pdf.get_y() > 262:
                pdf.add_page()
                _table_header(["CAMPO", "VALOR"], [75, 105])
            pdf.set_fill_color(233, 241, 255) if alternado else pdf.set_fill_color(248, 250, 255)
            pdf.cell(75, 7, _sanitize(k[:45]), fill=True)
            pdf.cell(105, 7, _sanitize(v[:65]), fill=True, new_x="LMARGIN", new_y="NEXT")
            alternado = not alternado
        pdf.ln(4)

    # ── Texto libre ──────────────────────────────────────────────
    if prose_lines:
        pdf.set_font("Helvetica", size=10)
        for line in prose_lines:
            if pdf.get_y() > 262:
                pdf.add_page()
            pdf.multi_cell(0, 6, _sanitize(line), new_x="LMARGIN", new_y="NEXT")

    # ── Pie de página ────────────────────────────────────────────
    pdf.set_y(-15)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 5, _sanitize(f"Pagina {pdf.page_no()}  |  Consultor IA"), align="C")

    return bytes(pdf.output())


@router.post("/query")
def query(request: QueryRequest):
    """
    Recibe una pregunta en lenguaje natural, busca contexto en PostgreSQL y responde con IA.
    Política DEFAULT DENY: la pregunta debe pasar validación ACL antes de tocar la DB.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    # ── ACL: validar intención antes de cualquier acceso a DB ─────────────────
    allowed, reason = validate_question(request.question)
    if not allowed:
        blocked_msg = f"Solicitud bloqueada: {reason}"
        if _wants_pdf(request.question):
            pdf_bytes = _build_pdf(title=request.question, content=blocked_msg)
            return Response(content=pdf_bytes, media_type="application/pdf",
                            headers={"Content-Disposition": "attachment; filename=respuesta.pdf"})
        return QueryResponse(
            question=request.question, context_found=0,
            answer=blocked_msg, provider_used="none"
        )

    # ── Cache: si hay extra_params no usamos cache (config distinta por cliente) ───
    use_cache = not request.extra_params
    cached = get_cached_response(request.question) if use_cache else None
    if cached and not _wants_pdf(request.question):
        return QueryResponse(
            question=request.question,
            context_found=cached["context_count"],
            answer=cached["answer"],
            data=None,
            provider_used=f"{cached['provider']} (cache)"
        )

    # ── Búsqueda en DB (pasa por firewall en searcher.py) ──────────────────────
    context = search_relevant_data(request.question, extra_params=request.extra_params)

    if context == ACCESS_DENIED:
        denied_msg = "No tengo acceso a esa información. Por favor no insistir."
        if _wants_pdf(request.question):
            pdf_bytes = _build_pdf(title=request.question, content=denied_msg)
            return Response(content=pdf_bytes, media_type="application/pdf",
                            headers={"Content-Disposition": "attachment; filename=respuesta.pdf"})
        return QueryResponse(question=request.question, context_found=0,
                             answer=denied_msg, provider_used="none")
    system_ctx = (request.extra_params or {}).get("contexto")
    answer = ask_ai(request.question, context, provider=request.provider, system_context=system_ctx)
    provider_used = request.provider or "default (.env)"

    # data siempre viene de la DB — no depende del modelo de IA
    data_rows = [r["datos"] for r in context] if context else []

    # Limpiar bloque __JSON_DATA__ del answer (solo se usa para el PDF)
    _, answer_clean = _extract_json_block(answer)

    if _wants_pdf(request.question):
        pdf_bytes = _build_pdf(title=request.question, content=answer)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=respuesta.pdf"}
        )

    # Guardar en cache solo si no hubo extra_params
    if use_cache:
        save_to_cache(request.question, answer_clean, len(context), provider_used)

    return QueryResponse(
        question=request.question,
        context_found=len(context),
        answer=answer_clean,
        data=data_rows if data_rows else None,
        provider_used=provider_used
    )

