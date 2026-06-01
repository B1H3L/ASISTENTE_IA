"""
pdf_builder.py
==============
Genera PDFs para el sistema Consultor IA.
- build_pdf_reporte()       : PDF genérico de respuesta/reporte
- build_pdf_planificacion() : PDF de sesión de aprendizaje (diseño oficial peruano)
"""

from __future__ import annotations

import json
import re
from datetime import date as _date

from fpdf import FPDF

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades comunes
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize(text: str) -> str:
    """Convierte a latin-1 (fpdf2 Helvetica) reemplazando caracteres no soportados."""
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00b0": "°",
        "\u00e9": "e", "\u00e1": "a", "\u00ed": "i", "\u00f3": "o",
        "\u00fa": "u", "\u00c9": "E", "\u00c1": "A", "\u00cd": "I",
        "\u00d3": "O", "\u00da": "U", "\u00fc": "u", "\u00f1": "n",
        "\u00d1": "N", "\u00bf": "?", "\u00a1": "!",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def extract_json_block(text: str) -> tuple[list | dict | None, str]:
    """
    Separa el bloque __JSON_DATA__ del texto limpio.
    Retorna (datos_json_o_None, texto_sin_bloque_json).
    """
    sep = "__JSON_DATA__"
    if sep in text:
        parts = text.split(sep, 1)
        human = parts[0].rstrip()
        raw_block = parts[1]
        match = re.search(r"```json\s*(.*?)\s*```", raw_block, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1)), human
            except json.JSONDecodeError:
                pass
        # fallback: buscar cualquier array u objeto JSON
        match = re.search(r"[\[{].*[\]}]", raw_block, re.DOTALL)
        if match:
            try:
                return json.loads(match.group()), human
            except json.JSONDecodeError:
                pass
        return None, human
    return None, text


# ─────────────────────────────────────────────────────────────────────────────
# PDF genérico de reporte
# ─────────────────────────────────────────────────────────────────────────────

def build_pdf_reporte(title: str, content: str) -> bytes:
    """PDF sencillo de respuesta/reporte."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", style="B", size=14)
    pdf.multi_cell(0, 8, _sanitize(title), align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6, _sanitize(content))
    return bytes(pdf.output())



# Mapa de etiquetas del texto estructurado que devuelve la IA
_KEY_MAP: dict[str, str] = {
    "TITULO":                "titulo",
    "PROPOSITO":             "proposito",
    "COMPETENCIA":           "competencia",
    "CAPACIDAD":             "capacidad",
    "DESEMPENO":             "desempeno",
    "DESEMPENO PRECISADO":   "desempeno",
    "EVIDENCIAS":            "evidencias",
    "EVIDENCIAS DE APRENDIZAJE": "evidencias",
    "INSTRUMENTO":           "instrumento",
    "INSTRUMENTO DE EVALUACION": "instrumento",
    "INICIO":                "inicio",
    "MATERIALES_INICIO":     "materiales_inicio",
    "TIEMPO_INICIO":         "tiempo_inicio",
    "DESARROLLO":            "desarrollo",
    "MATERIALES_DESARROLLO": "materiales_desarrollo",
    "TIEMPO_DESARROLLO":     "tiempo_desarrollo",
    "SALIDA":                "salida",
    "CIERRE":                "salida",
    "MATERIALES_SALIDA":     "materiales_salida",
    "MATERIALES_CIERRE":     "materiales_salida",
    "TIEMPO_SALIDA":         "tiempo_salida",
    "TIEMPO_CIERRE":         "tiempo_salida",
}

_KEY_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(k) for k in sorted(_KEY_MAP, key=len, reverse=True)) + r")\s*:\s*",
    re.IGNORECASE,
)


def _parse_planeamiento(content: str) -> dict:
    """Parsea el texto estructurado que genera la IA para el planeamiento."""
    result: dict[str, str] = {v: "" for v in _KEY_MAP.values()}
    current_key: str | None = None
    lines = content.splitlines()

    for raw_line in lines:
        line = raw_line.strip()
        m = _KEY_PATTERN.match(line)
        if m:
            tag = m.group(1).upper()
            current_key = _KEY_MAP.get(tag)
            value = line[m.end():].strip()
            if current_key:
                result[current_key] = value
        elif current_key:
            if result[current_key]:
                result[current_key] += "\n" + line
            else:
                result[current_key] = line

    return result


class _PlanPDF(FPDF):
    """FPDF con logo institucional y número de página en cada hoja."""

    def __init__(self, escudo_path: str = "", institucion: str = "",
                 ugel: str = "", director: str = ""):
        super().__init__()
        self._escudo = escudo_path
        self._institucion = institucion
        self._ugel = ugel
        self._director = director

    def header(self):
        self.set_margins(15, 15, 15)
        x0 = self.l_margin
        logo_w = 0
        if self._escudo:
            try:
                self.image(self._escudo, x=x0, y=self.t_margin, w=20, h=20)
                logo_w = 22
            except Exception:
                pass

        self.set_font("Helvetica", style="B", size=11)
        self.set_xy(x0 + logo_w, self.t_margin + 3)
        self.cell(0, 7, _sanitize(self._institucion or "INSTITUCION EDUCATIVA"),
                  new_x="LMARGIN", new_y="NEXT")

        if self._ugel:
            self.set_font("Helvetica", size=9)
            self.set_x(x0 + logo_w)
            self.cell(0, 5, _sanitize(self._ugel), new_x="LMARGIN", new_y="NEXT")

        self.set_y(self.t_margin + 22)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120, 120, 120)
        today = _date.today().strftime("%d/%m/%Y")
        self.cell(0, 5,
                  _sanitize(f"Pagina {self.page_no()} | Consultor IA | {today}"),
                  align="C")
        self.set_text_color(0, 0, 0)


def _mc_row(pdf: FPDF, cells: list[tuple[str, float, str]], line_h: float = 5,
            align: str = "L") -> None:
    """
    Dibuja una fila de multi_cell con la misma altura para todas las celdas.
    cells: lista de (texto, ancho_mm, font_style)  — font_style: "B", "I", "BI", ""
    """
    y0 = pdf.get_y()
    x0 = pdf.l_margin

    max_lines = 1
    for text, w, style in cells:
        pdf.set_font("Helvetica", style=style, size=8)
        dry = pdf.multi_cell(w, line_h, _sanitize(str(text)),
                             dry_run=True, output="LINES")
        max_lines = max(max_lines, len(dry))
    row_h = max_lines * line_h + 2

    x = x0
    for text, w, style in cells:
        pdf.rect(x, y0, w, row_h)
        x += w

    x = x0
    for text, w, style in cells:
        pdf.set_font("Helvetica", style=style, size=8)
        dry = pdf.multi_cell(w, line_h, _sanitize(str(text)),
                             dry_run=True, output="LINES")
        n = len(dry)
        text_h = n * line_h
        pdf.set_xy(x, y0 + (row_h - text_h) / 2)
        pdf.multi_cell(w, line_h, _sanitize(str(text)), border=0,
                       align=align, new_x="LMARGIN", new_y="NEXT")
        x += w

    pdf.set_xy(x0, y0 + row_h)


def _datos_row(pdf: FPDF,
               fields: list[tuple[str, float, str, float]],
               line_h: float = 5) -> None:
    """
    Dibuja la fila única de datos informativos estilo referencia.
    fields = [(label, lbl_w_mm, value, val_w_mm), ...]
    Etiqueta: gris+bold | Valor: blanco+italic — una sola fila, height auto.
    """
    y0 = pdf.get_y()
    x0 = pdf.l_margin

    # 1) Calcular altura máxima de todos los fragmentos
    max_lines = 1
    for label, lbl_w, value, val_w in fields:
        pdf.set_font("Helvetica", style="B", size=8)
        dry_lbl = pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)),
                                 dry_run=True, output="LINES")
        pdf.set_font("Helvetica", style="I", size=8)
        dry_val = pdf.multi_cell(val_w, line_h, _sanitize(str(value)),
                                 dry_run=True, output="LINES")
        max_lines = max(max_lines, len(dry_lbl), len(dry_val))

    row_h = max_lines * line_h + 4  # padding vertical

    # 2) Dibujar rectángulos alternos (gris=etiqueta, blanco=valor)
    x = x0
    for label, lbl_w, value, val_w in fields:
        pdf.set_fill_color(210, 210, 210)  # gris etiqueta
        pdf.rect(x, y0, lbl_w, row_h, style="FD")
        x += lbl_w
        pdf.set_fill_color(255, 255, 255)  # blanco valor
        pdf.rect(x, y0, val_w, row_h, style="FD")
        x += val_w

    # 3) Texto centrado verticalmente en cada celda
    x = x0
    for label, lbl_w, value, val_w in fields:
        # Etiqueta
        pdf.set_font("Helvetica", style="B", size=8)
        dry_lbl = pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)),
                                 dry_run=True, output="LINES")
        n_lbl = len(dry_lbl)
        pdf.set_xy(x, y0 + (row_h - n_lbl * line_h) / 2)
        pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)),
                       border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        x += lbl_w

        # Valor
        pdf.set_font("Helvetica", style="I", size=8)
        dry_val = pdf.multi_cell(val_w, line_h, _sanitize(str(value)),
                                 dry_run=True, output="LINES")
        n_val = len(dry_val)
        pdf.set_xy(x, y0 + (row_h - n_val * line_h) / 2)
        pdf.multi_cell(val_w, line_h, _sanitize(str(value)),
                       border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        x += val_w

    pdf.set_xy(x0, y0 + row_h)


def _is_subtitle(line: str) -> bool:
    """Detecta subtítulos dentro del texto de actividades (ej: PROBLEMATIZACION:).
    Criterio: línea en MAYÚSCULAS que termina en ':' y no empieza con número.
    """
    s = line.strip()
    if not s or len(s) < 3:
        return False
    if s[0].isdigit() or s[0] in "-•*·":
        return False
    return s.endswith(":") and s.upper() == s


# ─────────────────────────────────────────────────────────────────────────────
# Función principal de planificación
# ─────────────────────────────────────────────────────────────────────────────

def build_pdf_planificacion(title: str, content: str, extra: dict) -> bytes:
    """PDF con diseño oficial de planificación educativa peruana."""

    parsed = _parse_planeamiento(content)

    # ── Configuración del documento ──────────────────────────────────────────
    pdf = _PlanPDF(
        escudo_path = extra.get("escudo", ""),
        institucion = extra.get("institucion", "INSTITUCION EDUCATIVA"),
        ugel        = extra.get("ugel", ""),
        director    = extra.get("director", ""),
    )
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    subtipo  = extra.get("subtipo", "sesion").lower()
    numero   = extra.get("numero", "")
    periodo  = extra.get("periodo", "")

    LH = 5  # line height base

    # ── Título del documento ─────────────────────────────────────────────────
    if subtipo == "sesion":
        doc_label = "SESION DE APRENDIZAJE"
        if numero:
            doc_label += f"  -  N\u00b0 {numero}"
        if periodo:
            doc_label += f"  -  {periodo} BIMESTRE"
    else:
        doc_label = title.upper()

    pdf.set_font("Helvetica", style="B", size=13)
    pdf.cell(0, 8, _sanitize(doc_label), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── I. DATOS INFORMATIVOS ────────────────────────────────────────────────
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 7, "I.  DATOS INFORMATIVOS", new_x="LMARGIN", new_y="NEXT")

    grado_val = " ".join(filter(None, [extra.get("grado", ""), extra.get("nivel", "")]))
    _salon = extra.get("salon", extra.get("seccion", ""))
    if _salon:
        grado_val += f"\n\"Secc. {_salon}\""

    _datos_row(pdf, [
        ("AREA",          12,  extra.get("curso",   extra.get("area",  "")),   26),
        ("DOCENTE",       22,  extra.get("docente", extra.get("profesor", "")), 36),
        ("GRADO Y\nSECCION", 22, grado_val,                                    24),
        ("FECHA",         12,  extra.get("fecha", _date.today().strftime("%d/%m/%Y")), 26),
    ])
    pdf.ln(3)

    # ── II. TÍTULO DE LA SESIÓN ──────────────────────────────────────────────
    titulo_sesion = parsed.get("titulo", extra.get("tema", title))
    pdf.set_font("Helvetica", style="B", size=10)
    lbl2 = "II.  TITULO DE LA SESION:  "
    pdf.cell(pdf.get_string_width(lbl2), 6, _sanitize(lbl2))
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.multi_cell(0, 6, _sanitize(f'"{titulo_sesion}"'),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # ── III. PROPÓSITO ───────────────────────────────────────────────────────
    proposito = parsed.get("proposito", "")
    pdf.set_font("Helvetica", style="B", size=10)
    lbl3 = "III.  PROPOSITO DE LA SESION:  "
    pdf.cell(pdf.get_string_width(lbl3), 6, _sanitize(lbl3))
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.multi_cell(0, 6, _sanitize(f'"{proposito}"'),
                   align="J", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── Tabla de competencias ────────────────────────────────────────────────
    competencia = parsed.get("competencia", "")
    capacidad   = parsed.get("capacidad",   "")
    desempeno   = parsed.get("desempeno",   "")
    evidencias  = parsed.get("evidencias",  "")
    instrumento = parsed.get("instrumento", "")

    # Columnas: [texto_header, ancho_mm]
    COMP_COLS = [
        ("COMPETENCIA",                 38),
        ("CAPACIDAD",                   33),
        ("DESEMPENO PRECISADO",         43),
        ("EVIDENCIAS DE APRENDIZAJE",   36),
        ("INSTRUMENTO DE EVALUACION",   30),
    ]
    HDR_H = 14  # altura fija del header de competencias

    # Fila header: rects grises + texto centrado
    pdf.set_fill_color(210, 210, 210)
    y_ch = pdf.get_y()
    x = pdf.l_margin
    for hdr, w in COMP_COLS:
        pdf.rect(x, y_ch, w, HDR_H, style="FD")
        x += w

    pdf.set_font("Helvetica", style="B", size=8)
    x = pdf.l_margin
    for hdr, w in COMP_COLS:
        dry = pdf.multi_cell(w, LH, _sanitize(hdr), dry_run=True, output="LINES")
        n = len(dry)
        text_h = n * LH
        pdf.set_xy(x, y_ch + (HDR_H - text_h) / 2)
        pdf.multi_cell(w, LH, _sanitize(hdr), border=0,
                       align="C", new_x="LMARGIN", new_y="NEXT")
        x += w
    pdf.set_xy(pdf.l_margin, y_ch + HDR_H)

    # Fila de datos: altura calculada con dry_run
    vals = [competencia, capacidad, desempeno, evidencias, instrumento]
    data_cells = [(v, c[1], "I") for v, c in zip(vals, COMP_COLS)]
    _mc_row(pdf, data_cells, line_h=LH, align="C")
    pdf.ln(3)

    # ── IV. SECUENCIA DE APRENDIZAJE ─────────────────────────────────────────
    # Columnas: Actividades | Materiales | Tiempo
    ACT_W  = 130
    MAT_W  = 37
    TMP_W  = 13
    FULL_W = ACT_W + MAT_W + TMP_W  # 180 mm
    HDR_SEQ = 9

    _min_seq = 7 + HDR_SEQ + 4 * LH
    if pdf.h - pdf.b_margin - pdf.get_y() < _min_seq:
        pdf.add_page()

    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 7, "IV.  SECUENCIA DE APRENDIZAJE", new_x="LMARGIN", new_y="NEXT")
    y_sh = pdf.get_y()
    pdf.set_fill_color(210, 210, 210)
    pdf.rect(pdf.l_margin,              y_sh, ACT_W, HDR_SEQ, style="FD")
    pdf.rect(pdf.l_margin + ACT_W,      y_sh, MAT_W, HDR_SEQ, style="FD")
    pdf.rect(pdf.l_margin + ACT_W + MAT_W, y_sh, TMP_W, HDR_SEQ, style="FD")

    pdf.set_font("Helvetica", style="B", size=9)
    pdf.set_xy(pdf.l_margin, y_sh + 1)
    pdf.cell(ACT_W, HDR_SEQ - 2,
             _sanitize("ACTIVIDADES Y ESTRATEGIAS DE APRENDIZAJE"),
             border=0, align="C")
    pdf.set_font("Helvetica", style="B", size=7)
    pdf.set_xy(pdf.l_margin + ACT_W, y_sh + 1)
    pdf.cell(MAT_W, HDR_SEQ - 2,
             _sanitize("MATERIALES/RECURSOS"), border=0, align="C")
    pdf.set_xy(pdf.l_margin + ACT_W + MAT_W, y_sh + 1)
    pdf.cell(TMP_W, HDR_SEQ - 2, _sanitize("TIEMPO"), border=0, align="C")
    pdf.set_xy(pdf.l_margin, y_sh + HDR_SEQ)

    phases = [
        ("INICIO",     "inicio",     "materiales_inicio",     "tiempo_inicio",     "15'"),
        ("DESARROLLO", "desarrollo", "materiales_desarrollo", "tiempo_desarrollo", "45'"),
        ("SALIDA",     "salida",     "materiales_salida",     "tiempo_salida",     "10'"),
    ]

    x_acts = pdf.l_margin
    x_mats = pdf.l_margin + ACT_W
    x_tmp  = pdf.l_margin + ACT_W + MAT_W

    for phase_label, key_act, key_mat, key_tmp, default_tmp in phases:
        actividades = parsed.get(key_act, "")
        materiales  = parsed.get(key_mat, "")
        tiempo      = parsed.get(key_tmp, default_tmp)
        if not actividades:
            continue

        # Normalizar tiempo
        if tiempo and not any(c in tiempo for c in ("'", "m", "\u2019")):
            tiempo = tiempo + "'"

        # ── Pre-calcular alturas (nombre de fase va dentro del bloque) ────
        act_content = phase_label + ":\n" + actividades
        pdf.set_font("Helvetica", size=9)
        act_lines_dry = pdf.multi_cell(ACT_W, LH, _sanitize(act_content),
                                       dry_run=True, output="LINES")
        act_h = len(act_lines_dry) * LH + 2

        mat_text = ("Materiales:\n" + materiales.strip()) if materiales.strip() else ""
        if mat_text:
            pdf.set_font("Helvetica", style="I", size=8)
            mat_lines_dry = pdf.multi_cell(MAT_W, LH, _sanitize(mat_text),
                                           dry_run=True, output="LINES")
            mat_h = len(mat_lines_dry) * LH + 2
        else:
            mat_h = 0

        row_h = max(act_h, mat_h, 3 * LH)

        # ── Anti-huérfano: saltar si queda menos de 4 líneas ─────────────
        remaining = pdf.h - pdf.b_margin - pdf.get_y()
        if remaining < 4 * LH:
            pdf.add_page()
        remaining = pdf.h - pdf.b_margin - pdf.get_y()

        if row_h <= remaining:
            # ── Opción A: bloque completo cabe en esta página ─────────────
            y0 = pdf.get_y()

            # Tres rects con mismo alto → "hueco" vacío en materiales y tiempo
            pdf.rect(x_acts, y0, ACT_W, row_h)
            pdf.rect(x_mats, y0, MAT_W, row_h)
            pdf.rect(x_tmp,  y0, TMP_W, row_h)

            # Nombre de fase: primera línea dentro del rect (bold-italic)
            pdf.set_xy(x_acts, y0 + 1)
            pdf.set_font("Helvetica", style="BI", size=9)
            pdf.cell(ACT_W, LH, _sanitize(phase_label + ":"), border=0,
                     new_x="LMARGIN", new_y="NEXT")

            # Actividades
            for _raw in actividades.split("\n"):
                _line = _raw.strip()
                if not _line:
                    pdf.set_font("Helvetica", size=9)
                    pdf.cell(ACT_W, 2, "", new_x="LMARGIN", new_y="NEXT")
                    continue
                pdf.set_font("Helvetica",
                             style="B" if _is_subtitle(_line) else "", size=9)
                pdf.multi_cell(ACT_W, LH, _sanitize(_line), border=0,
                               new_x="LMARGIN", new_y="NEXT")

            # Materiales (parte superior del rect, hueco abajo)
            if mat_text:
                pdf.set_font("Helvetica", style="I", size=8)
                pdf.set_xy(x_mats, y0 + 1)
                pdf.multi_cell(MAT_W, LH, _sanitize(mat_text), border=0,
                               new_x="LMARGIN", new_y="NEXT")

            # Tiempo centrado verticalmente en columna de tiempo
            pdf.set_font("Helvetica", style="B", size=9)
            pdf.set_xy(x_tmp, y0 + (row_h - LH) / 2)
            pdf.cell(TMP_W, LH, _sanitize(tiempo), border=0, align="C",
                     new_x="LMARGIN", new_y="NEXT")

            pdf.set_xy(x_acts, y0 + row_h)

        else:
            # ── Opción B: actividades largas → fluyen a páginas siguientes ─
            y0 = pdf.get_y()
            remaining_b = pdf.h - pdf.b_margin - y0

            # Rects de materiales y tiempo cubren todo el espacio restante
            # (texto al tope, hueco vacío abajo)
            pdf.rect(x_mats, y0, MAT_W, remaining_b)
            pdf.rect(x_tmp,  y0, TMP_W, remaining_b)

            # Materiales: auto_page_break=False para no desplazar el cursor
            if mat_text:
                pdf.set_auto_page_break(False)
                pdf.set_font("Helvetica", style="I", size=8)
                pdf.set_xy(x_mats, y0 + 1)
                pdf.multi_cell(MAT_W, LH, _sanitize(mat_text), border=0,
                               new_x="LMARGIN", new_y="NEXT")
                pdf.set_auto_page_break(True, margin=15)

            # Tiempo en mitad vertical del rect de tiempo
            pdf.set_font("Helvetica", style="B", size=9)
            pdf.set_xy(x_tmp, y0 + remaining_b / 2 - LH / 2)
            pdf.cell(TMP_W, LH, _sanitize(tiempo), border=0, align="C",
                     new_x="LMARGIN", new_y="NEXT")

            # Nombre de fase + actividades fluyen en columna izquierda con LR
            pdf.set_xy(x_acts, y0)
            pdf.set_font("Helvetica", style="BI", size=9)
            pdf.multi_cell(ACT_W, LH, _sanitize(phase_label + ":"), border="LR",
                           new_x="LMARGIN", new_y="NEXT")
            for _raw in actividades.split("\n"):
                _line = _raw.strip()
                if not _line:
                    pdf.set_font("Helvetica", size=9)
                    pdf.cell(ACT_W, 2, "", border="LR",
                             new_x="LMARGIN", new_y="NEXT")
                    continue
                pdf.set_font("Helvetica",
                             style="B" if _is_subtitle(_line) else "", size=9)
                pdf.multi_cell(ACT_W, LH, _sanitize(_line), border="LR",
                               new_x="LMARGIN", new_y="NEXT")

            # Línea de cierre del bloque de actividades
            y_close = pdf.get_y()
            pdf.set_draw_color(0, 0, 0)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, y_close, pdf.l_margin + FULL_W, y_close)

    return bytes(pdf.output())
