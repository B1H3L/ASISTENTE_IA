from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal
from searcher import search_relevant_data, ACCESS_DENIED
from ai_client import ask_ai, ask_ai_planeamiento, ask_ai_libro, ask_ai_formulario
from acl import validate_question
from query_cache import get_cached_response, save_to_cache
from pdf_builder import build_pdf_reporte, build_pdf_planificacion, build_pdf_libro, extract_json_block
import config
from logger import app_log, security_log

router = APIRouter()

PDF_KEYWORDS = {"pdf", "archivo", "descarga", "documento", "reporte", "informe", "exportar"}
_RESERVED_EXTRA_KEYS = {"tablas", "alias", "contexto", "tipo", "formato", "subtipo"}


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    question: str
    provider: Literal["claude", "gpt", "github"] | None = None
    extra_params: dict | None = None

    @field_validator("question")
    @classmethod
    def _check_length(cls, v: str) -> str:
        if len(v) > config.MAX_QUESTION_LENGTH:
            raise ValueError(f"Pregunta demasiado larga. Máximo {config.MAX_QUESTION_LENGTH} caracteres.")
        return v


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
    fields = {k: v for k, v in extra.items() if k not in _RESERVED_EXTRA_KEYS}
    base = extra.get("contexto", "")
    parts = ([base] if base else []) + [f"{k}: {v}" for k, v in fields.items()]
    return "\n".join(parts) or None


@router.post("/query")
def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    extra = {**(request.model_extra or {}), **(request.extra_params or {})}
    api_key: str | None = extra.pop("api_key", None) or None

    app_log.info("QUERY | provider=%s | q_len=%d", request.provider or "default", len(request.question))

    # validación ACL
    allowed, reason = validate_question(request.question)
    if not allowed:
        security_log.warning("ACL_BLOCK | reason=%s | q=%.120s", reason, request.question)
        msg = f"Solicitud bloqueada: {reason}"
        if _wants_pdf(request.question):
            return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, msg))
        return QueryResponse(question=request.question, context_found=0, answer=msg, provider_used="none")

    # cache
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

    # modo libro
    if extra.get("tipo", "").lower() == "libro":
        import json as _json
        contexto = extra.get("contexto", request.question)
        instrucciones = extra.get("instrucciones", "")
        try:
            num_secciones = int(extra["num_secciones"]) if extra.get("num_secciones") else None
        except (ValueError, TypeError):
            num_secciones = None
        if num_secciones is None:
            import re as _re
            _m = _re.search(r"\b(\d+)\s*p[aá]ginas?\b", request.question, _re.IGNORECASE)
            if _m:
                num_secciones = int(_m.group(1))
        if num_secciones is not None:
            instrucciones = (instrucciones + f"\nGenera exactamente {num_secciones} secciones.").strip()
        answer = ask_ai_libro(contexto, instrucciones, provider=request.provider, api_key=api_key)
        wants_pdf = extra.get("formato", "").lower() == "pdf" or _wants_pdf(request.question)
        if wants_pdf:
            try:
                libro_data = _json.loads(answer)
            except _json.JSONDecodeError:
                libro_data = {"titulo": contexto[:60], "tagline": "", "secciones": [],
                              "stats": [], "conclusion": answer, "contacto": {}}
            return _pdf_response("libro.pdf", build_pdf_libro(libro_data))
        return QueryResponse(question=request.question, context_found=0, answer=answer,
                             data=None, provider_used=request.provider or "default (.env)")

    # modo formulario
    if extra.get("tipo", "").lower() == "formulario":
        import json as _json
        contexto = extra.get("contexto", "")
        answer = ask_ai_formulario(request.question, contexto, provider=request.provider, api_key=api_key)
        try:
            formulario_data = _json.loads(answer)
        except _json.JSONDecodeError:
            formulario_data = None
        return QueryResponse(
            question=request.question,
            context_found=0,
            answer=answer,
            data=[formulario_data] if formulario_data else None,
            provider_used=request.provider or "default (.env)",
        )

    # modo planeamiento
    if extra.get("tipo", "").lower() == "planeamiento":
        contexto = _build_system_ctx(extra) or ""
        answer = ask_ai_planeamiento(request.question, contexto, provider=request.provider, api_key=api_key)
        wants_pdf = extra.get("formato", "").lower() == "pdf" or _wants_pdf(request.question)
        if wants_pdf:
            return _pdf_response("planeamiento.pdf", build_pdf_planificacion(request.question, answer, extra))
        return QueryResponse(question=request.question, context_found=0, answer=answer,
                             data=None, provider_used=request.provider or "default (.env)")

    # búsqueda en DB
    context = search_relevant_data(request.question, extra_params=request.extra_params)

    if context == ACCESS_DENIED:
        msg = "No tengo acceso a esa informacion. Por favor no insistir."
        if _wants_pdf(request.question):
            return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, msg))
        return QueryResponse(question=request.question, context_found=0, answer=msg, provider_used="none")

    system_ctx = _build_system_ctx(extra)
    answer = ask_ai(request.question, context, provider=request.provider,
                    system_context=system_ctx, api_key=api_key)
    provider_used = request.provider or "default (.env)"
    data_rows = [r["datos"] for r in context] if context else []
    _, answer_clean = extract_json_block(answer)

    if _wants_pdf(request.question):
        return _pdf_response("respuesta.pdf", build_pdf_reporte(request.question, answer))

    if use_cache and not answer_clean.startswith("Error:"):
        save_to_cache(request.question, answer_clean, len(context), provider_used)

    return QueryResponse(
        question=request.question,
        context_found=len(context),
        answer=answer_clean,
        data=data_rows if data_rows else None,
        provider_used=provider_used,
    )
