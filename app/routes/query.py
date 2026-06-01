from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from typing import Literal
from searcher import search_relevant_data, ACCESS_DENIED
from ai_client import ask_ai, ask_ai_planeamiento
from acl import validate_question
from query_cache import get_cached_response, save_to_cache
from pdf_builder import build_pdf_reporte, build_pdf_planificacion, extract_json_block

router = APIRouter()

PDF_KEYWORDS = {"pdf", "archivo", "descarga", "documento", "reporte", "informe", "exportar"}

_RESERVED_EXTRA_KEYS = {"tablas", "alias", "contexto", "tipo", "formato", "subtipo"}


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # acepta campos planos del cliente PHP
    question: str
    provider: Literal["ollama", "claude", "gpt", "github"] | None = None
    extra_params: dict | None = None
    # extra_params acepta cualquier clave que el sistema cliente quiera enviar.
    # Claves reconocidas:
    #   "tablas":   list[str]       -> tablas a consultar (deben estar en ALLOWED_TABLES)
    #   "contexto": str             -> contexto libre que la IA recibe en el prompt
    #   "alias":    dict[str, str]  -> {nombre_logico: tabla_real_en_db}
    #   "tipo":     str             -> "planeamiento" activa el modo de generación educativa
    #   "subtipo":  str             -> "sesion" | "unidad" | "anual" | "silabus" | "cartel"
    #   "formato":  str             -> "pdf" devuelve PDF aunque la pregunta no lo mencione
    #   Cualquier otra clave se inyecta como contexto adicional a la IA


class QueryResponse(BaseModel):
    question: str
    context_found: int
    answer: str
    data: list[dict] | None = None
    provider_used: str


def _wants_pdf(question: str) -> bool:
    words = {w.strip("¿?.,;:").lower() for w in question.split()}
    return bool(words & PDF_KEYWORDS)


def _pdf_response(filename: str, content_bytes: bytes) -> Response:
    return Response(
        content=content_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _build_system_ctx(extra: dict) -> str | None:
    """Combina 'contexto' + campos no reservados en un texto para la IA."""
    fields = {k: v for k, v in extra.items() if k not in _RESERVED_EXTRA_KEYS}
    base   = extra.get("contexto", "")
    parts  = ([base] if base else []) + [f"{k}: {v}" for k, v in fields.items()]
    return "\n".join(parts) or None


@router.post("/query")
def query(request: QueryRequest):
    """
    Recibe una pregunta en lenguaje natural, busca contexto en PostgreSQL y responde con IA.
    Política DEFAULT DENY: la pregunta debe pasar validación ACL antes de tocar la DB.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    # Campos planos del nivel raíz (cliente PHP) + extra_params (extra_params gana)
    extra = {**(request.model_extra or {}), **(request.extra_params or {})}

    # ── ACL ───────────────────────────────────────────────────────────────────
    allowed, reason = validate_question(request.question)
    if not allowed:
        msg = f"Solicitud bloqueada: {reason}"
        if _wants_pdf(request.question):
            return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, msg))
        return QueryResponse(question=request.question, context_found=0,
                             answer=msg, provider_used="none")

    # ── Cache ─────────────────────────────────────────────────────────────────
    use_cache = not request.extra_params
    cached = get_cached_response(request.question) if use_cache else None
    if cached and not _wants_pdf(request.question):
        return QueryResponse(
            question=request.question,
            context_found=cached["context_count"],
            answer=cached["answer"],
            data=None,
            provider_used=f"{cached['provider']} (cache)",
        )

    # ── Modo planeamiento: genera contenido sin consultar DB ──────────────────
    if extra.get("tipo", "").lower() == "planeamiento":
        contexto = _build_system_ctx(extra) or ""
        answer   = ask_ai_planeamiento(request.question, contexto, provider=request.provider)
        wants_pdf = extra.get("formato", "").lower() == "pdf" or _wants_pdf(request.question)
        if wants_pdf:
            return _pdf_response("planeamiento.pdf",
                                 build_pdf_planificacion(request.question, answer, extra))
        return QueryResponse(question=request.question, context_found=0,
                             answer=answer, data=None,
                             provider_used=request.provider or "default (.env)")

    # ── Búsqueda en DB ────────────────────────────────────────────────────────
    context = search_relevant_data(request.question, extra_params=request.extra_params)

    if context == ACCESS_DENIED:
        msg = "No tengo acceso a esa informacion. Por favor no insistir."
        if _wants_pdf(request.question):
            return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, msg))
        return QueryResponse(question=request.question, context_found=0,
                             answer=msg, provider_used="none")

    system_ctx   = _build_system_ctx(extra)
    answer       = ask_ai(request.question, context, provider=request.provider,
                          system_context=system_ctx)
    provider_used = request.provider or "default (.env)"
    data_rows     = [r["datos"] for r in context] if context else []
    _, answer_clean = extract_json_block(answer)

    if _wants_pdf(request.question):
        return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, answer))

    if use_cache:
        save_to_cache(request.question, answer_clean, len(context), provider_used)

    return QueryResponse(
        question=request.question,
        context_found=len(context),
        answer=answer_clean,
        data=data_rows if data_rows else None,
        provider_used=provider_used,
    )
