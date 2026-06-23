from __future__ import annotations

import json
import re
from datetime import date as _date

from fpdf import FPDF


def _sanitize(text: str) -> str:
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", "°": "°",
        "é": "e", "á": "a", "í": "i", "ó": "o",
        "ú": "u", "É": "E", "Á": "A", "Í": "I",
        "Ó": "O", "Ú": "U", "ü": "u", "ñ": "n",
        "Ñ": "N", "¿": "?", "¡": "!",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def extract_json_block(text: str) -> tuple[list | dict | None, str]:
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
        # fallback: cualquier array u objeto JSON
        match = re.search(r"[\[{].*[\]}]", raw_block, re.DOTALL)
        if match:
            try:
                return json.loads(match.group()), human
            except json.JSONDecodeError:
                pass
        return None, human
    return None, text


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 41, 128, 185


def _lighten(r: int, g: int, b: int, factor: float = 0.35) -> tuple[int, int, int]:
    return (
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )


class _LibroPDF(FPDF):
    def __init__(self, color_primario: str = "#2c3e50", titulo: str = ""):
        super().__init__()
        self._pr, self._pg, self._pb = _hex_to_rgb(color_primario)
        self._lr, self._lg, self._lb = _lighten(self._pr, self._pg, self._pb, 0.6)
        self._titulo = titulo
        self.set_margins(0, 0, 0)
        self.set_auto_page_break(auto=False)

    def _full_bg(self, r: int, g: int, b: int) -> None:
        self.set_fill_color(r, g, b)
        self.rect(0, 0, self.w, self.h, style="F")

    def _accent_bar(self, y: float, h: float = 1.5) -> None:
        self.set_fill_color(self._pr, self._pg, self._pb)
        self.rect(0, y, self.w, h, style="F")

    def _header_band(self, y: float, height: float, text: str, font_size: int = 11) -> None:
        self.set_fill_color(self._pr, self._pg, self._pb)
        self.rect(0, y, self.w, height, style="F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", style="B", size=font_size)
        self.set_xy(15, y + (height - font_size * 0.35) / 2)
        self.cell(self.w - 30, font_size * 0.35 + 1, _sanitize(text.upper()), border=0)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(-10)
        self.set_font("Helvetica", size=7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 5, _sanitize(f"  {self._titulo}  ·  Pagina {self.page_no()}"),
                  align="C", border=0)
        self.set_text_color(0, 0, 0)


def _libro_cover(pdf: _LibroPDF, data: dict) -> None:
    pdf.add_page()
    pdf._full_bg(pdf._pr, pdf._pg, pdf._pb)

    W, H = pdf.w, pdf.h
    M = 20

    # banda decorativa superior
    pdf.set_fill_color(pdf._lr, pdf._lg, pdf._lb)
    pdf.rect(0, 0, W, 8, style="F")

    # badge superior
    pdf.set_text_color(pdf._lr, pdf._lg, pdf._lb)
    pdf.set_font("Helvetica", style="B", size=8)
    pdf.set_xy(M, 14)
    pdf.cell(0, 5, _sanitize("LIBRO DIGITAL"), border=0)

    # título principal
    titulo = _sanitize(data.get("titulo", "Sin titulo"))
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", style="B", size=28)
    pdf.set_xy(M, H * 0.30)
    pdf.multi_cell(W - M * 2, 12, titulo, border=0, align="C")

    # línea divisora
    y_line = pdf.get_y() + 8
    pdf.set_fill_color(pdf._lr, pdf._lg, pdf._pb)
    pdf.rect(W / 2 - 25, y_line, 50, 2, style="F")

    # tagline
    tagline = _sanitize(data.get("tagline", ""))
    if tagline:
        pdf.set_text_color(220, 220, 220)
        pdf.set_font("Helvetica", style="I", size=12)
        pdf.set_xy(M, y_line + 10)
        pdf.multi_cell(W - M * 2, 7, tagline, border=0, align="C")

    # pie de página con web
    pdf.set_fill_color(pdf._lr, pdf._lg, pdf._lb)
    pdf.rect(0, H - 18, W, 1.5, style="F")
    contacto = data.get("contacto", {})
    web = _sanitize(contacto.get("web", ""))
    if web:
        pdf.set_text_color(200, 200, 200)
        pdf.set_font("Helvetica", size=8)
        pdf.set_xy(M, H - 14)
        pdf.cell(W - M * 2, 6, web, border=0, align="C")

    pdf.set_text_color(0, 0, 0)


def _libro_about(pdf: _LibroPDF, data: dict) -> None:
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    W = pdf.w
    M = 15

    pdf._header_band(0, 18, data.get("titulo", ""))
    y = 25

    # stats en cuadrícula 2x2
    stats = data.get("stats", [])[:4]
    if stats:
        box_w = (W - M * 2 - 6) / 2
        box_h = 22
        gap = 3
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.set_xy(M, y)
        for i, stat in enumerate(stats):
            col = i % 2
            row = i // 2
            bx = M + col * (box_w + gap)
            by = y + row * (box_h + gap)
            pdf.set_fill_color(pdf._lr, pdf._lg, pdf._lb)
            pdf.rect(bx, by, box_w, box_h, style="FD")
            pdf.set_text_color(pdf._pr, pdf._pg, pdf._pb)
            pdf.set_font("Helvetica", style="B", size=16)
            pdf.set_xy(bx + 4, by + 2)
            pdf.cell(box_w - 8, 10, _sanitize(str(stat.get("valor", ""))), border=0, align="C")
            pdf.set_text_color(80, 80, 80)
            pdf.set_font("Helvetica", size=7)
            pdf.set_xy(bx + 4, by + 13)
            pdf.cell(box_w - 8, 6, _sanitize(str(stat.get("etiqueta", ""))), border=0, align="C")
        y += 2 * (box_h + gap) + 8

    pdf.set_text_color(0, 0, 0)

    # qué es
    pdf._accent_bar(y, 1)
    y += 4
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.set_text_color(pdf._pr, pdf._pg, pdf._pb)
    pdf.set_xy(M, y)
    pdf.cell(0, 6, _sanitize("QUE ES"), border=0)
    y = pdf.get_y() + 7
    pdf.set_text_color(50, 50, 50)
    pdf.set_font("Helvetica", size=9)
    pdf.set_xy(M, y)
    pdf.multi_cell(W - M * 2, 5.5, _sanitize(data.get("que_es", "")), border=0, align="J")
    y = pdf.get_y() + 8

    # cómo ayuda
    pdf._accent_bar(y, 1)
    y += 4
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.set_text_color(pdf._pr, pdf._pg, pdf._pb)
    pdf.set_xy(M, y)
    pdf.cell(0, 6, _sanitize("COMO AYUDA"), border=0)
    y = pdf.get_y() + 7
    pdf.set_text_color(50, 50, 50)
    pdf.set_font("Helvetica", size=9)
    pdf.set_xy(M, y)
    pdf.multi_cell(W - M * 2, 5.5, _sanitize(data.get("como_ayuda", "")), border=0, align="J")

    pdf.set_text_color(0, 0, 0)
    pdf.set_auto_page_break(auto=False)


def _libro_section(pdf: _LibroPDF, seccion: dict, idx: int) -> None:
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    W, H = pdf.w, pdf.h
    M = 15

    label = f"SECCION {idx + 1}  ·  {seccion.get('titulo', '').upper()}"
    pdf._header_band(0, 18, label, font_size=9)
    y = 24

    descripcion = seccion.get("descripcion", "")
    if descripcion:
        pdf.set_font("Helvetica", style="I", size=9)
        pdf.set_text_color(100, 100, 100)
        pdf.set_xy(M, y)
        pdf.multi_cell(W - M * 2, 5.5, _sanitize(descripcion), border=0, align="J")
        y = pdf.get_y() + 6

    pdf._accent_bar(y, 1)
    y += 6

    # items en 2 columnas
    items = seccion.get("items", [])
    col_w = (W - M * 2 - 6) / 2
    col_gap = 6

    pdf.set_text_color(40, 40, 40)
    pdf.set_font("Helvetica", size=8.5)

    for i, item in enumerate(items):
        col = i % 2
        bx = M + col * (col_w + col_gap)
        pdf.set_fill_color(pdf._pr, pdf._pg, pdf._pb)
        pdf.ellipse(bx, y + 1.5, 2.5, 2.5, style="F")
        pdf.set_text_color(40, 40, 40)
        pdf.set_xy(bx + 5, y)
        line_count = pdf.multi_cell(col_w - 5, 5, _sanitize(str(item)),
                                    border=0, align="L",
                                    dry_run=True, output="LINES")
        pdf.set_xy(bx + 5, y)
        pdf.multi_cell(col_w - 5, 5, _sanitize(str(item)), border=0, align="L")

        if col == 1 or i == len(items) - 1:
            line_h = max(len(line_count), 1) * 5 + 3
            y += line_h
            if y > H - 25:
                pdf.add_page()
                pdf._header_band(0, 18, label, font_size=9)
                y = 24

    pdf.set_text_color(0, 0, 0)
    pdf.set_auto_page_break(auto=False)


def _libro_conclusion(pdf: _LibroPDF, data: dict) -> None:
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    W = pdf.w
    M = 15

    pdf._header_band(0, 18, "CONCLUSION", font_size=11)
    y = 28

    conclusion = data.get("conclusion", "")
    if conclusion:
        pdf.set_font("Helvetica", style="I", size=10)
        pdf.set_text_color(50, 50, 50)
        pdf.set_xy(M, y)
        pdf.multi_cell(W - M * 2, 6, _sanitize(conclusion), border=0, align="J")
        y = pdf.get_y() + 12

    # bloque de contacto
    contacto = data.get("contacto", {})
    if any(contacto.values()):
        pdf.set_fill_color(pdf._lr, pdf._lg, pdf._lb)
        pdf.rect(M, y, W - M * 2, 30, style="F")
        pdf.set_text_color(pdf._pr, pdf._pg, pdf._pb)
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.set_xy(M + 5, y + 5)
        pdf.cell(0, 6, _sanitize("CONTACTO"), border=0)
        pdf.set_text_color(50, 50, 50)
        pdf.set_font("Helvetica", size=9)
        contact_lines = []
        if contacto.get("email"):
            contact_lines.append(_sanitize(contacto["email"]))
        if contacto.get("telefono"):
            contact_lines.append(_sanitize(contacto["telefono"]))
        if contacto.get("web"):
            contact_lines.append(_sanitize(contacto["web"]))
        for j, line in enumerate(contact_lines):
            pdf.set_xy(M + 5, y + 14 + j * 6)
            pdf.cell(0, 5, line, border=0)

    pdf.set_text_color(0, 0, 0)
    pdf.set_auto_page_break(auto=False)


def build_pdf_libro(data: dict) -> bytes:
    if not isinstance(data, dict):
        data = {}
    color = data.get("color_primario", "#2c3e50")
    titulo = data.get("titulo", "Libro Digital")
    pdf = _LibroPDF(color_primario=color, titulo=titulo)
    _libro_cover(pdf, data)
    _libro_about(pdf, data)
    for i, seccion in enumerate(data.get("secciones", [])):
        _libro_section(pdf, seccion, i)
    _libro_conclusion(pdf, data)
    return bytes(pdf.output())


def build_pdf_reporte(title: str, content: str) -> bytes:
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


# mapa de etiquetas del texto estructurado de la IA
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
    result: dict[str, str] = {v: "" for v in _KEY_MAP.values()}
    current_key: str | None = None
    for raw_line in content.splitlines():
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
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120, 120, 120)
        today = _date.today().strftime("%d/%m/%Y")
        self.cell(0, 5, _sanitize(f"Pagina {self.page_no()} | Consultor IA | {today}"), align="C")
        self.set_text_color(0, 0, 0)


def _mc_row(pdf: FPDF, cells: list[tuple[str, float, str]], line_h: float = 5,
            align: str = "L") -> None:
    y0 = pdf.get_y()
    x0 = pdf.l_margin
    max_lines = 1
    for text, w, style in cells:
        pdf.set_font("Helvetica", style=style, size=8)
        dry = pdf.multi_cell(w, line_h, _sanitize(str(text)), dry_run=True, output="LINES")
        max_lines = max(max_lines, len(dry))
    row_h = max_lines * line_h + 2
    x = x0
    for text, w, style in cells:
        pdf.rect(x, y0, w, row_h)
        x += w
    x = x0
    for text, w, style in cells:
        pdf.set_font("Helvetica", style=style, size=8)
        dry = pdf.multi_cell(w, line_h, _sanitize(str(text)), dry_run=True, output="LINES")
        n = len(dry)
        text_h = n * line_h
        pdf.set_xy(x, y0 + (row_h - text_h) / 2)
        pdf.multi_cell(w, line_h, _sanitize(str(text)), border=0,
                       align=align, new_x="LMARGIN", new_y="NEXT")
        x += w
    pdf.set_xy(x0, y0 + row_h)


def _datos_row(pdf: FPDF, fields: list[tuple[str, float, str, float]], line_h: float = 5) -> None:
    y0 = pdf.get_y()
    x0 = pdf.l_margin

    # calcular altura máxima
    max_lines = 1
    for label, lbl_w, value, val_w in fields:
        pdf.set_font("Helvetica", style="B", size=8)
        dry_lbl = pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)), dry_run=True, output="LINES")
        pdf.set_font("Helvetica", style="I", size=8)
        dry_val = pdf.multi_cell(val_w, line_h, _sanitize(str(value)), dry_run=True, output="LINES")
        max_lines = max(max_lines, len(dry_lbl), len(dry_val))
    row_h = max_lines * line_h + 4

    # dibujar rectángulos etiqueta/valor alternos
    x = x0
    for label, lbl_w, value, val_w in fields:
        pdf.set_fill_color(210, 210, 210)
        pdf.rect(x, y0, lbl_w, row_h, style="FD")
        x += lbl_w
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(x, y0, val_w, row_h, style="FD")
        x += val_w

    # texto centrado verticalmente
    x = x0
    for label, lbl_w, value, val_w in fields:
        pdf.set_font("Helvetica", style="B", size=8)
        dry_lbl = pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)), dry_run=True, output="LINES")
        pdf.set_xy(x, y0 + (row_h - len(dry_lbl) * line_h) / 2)
        pdf.multi_cell(lbl_w, line_h, _sanitize(str(label)),
                       border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        x += lbl_w
        pdf.set_font("Helvetica", style="I", size=8)
        dry_val = pdf.multi_cell(val_w, line_h, _sanitize(str(value)), dry_run=True, output="LINES")
        pdf.set_xy(x, y0 + (row_h - len(dry_val) * line_h) / 2)
        pdf.multi_cell(val_w, line_h, _sanitize(str(value)),
                       border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        x += val_w
    pdf.set_xy(x0, y0 + row_h)


def _is_subtitle(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 3:
        return False
    if s[0].isdigit() or s[0] in "-•*·":
        return False
    return s.endswith(":") and s.upper() == s


def build_pdf_planificacion(title: str, content: str, extra: dict) -> bytes:
    parsed = _parse_planeamiento(content)

    pdf = _PlanPDF(
        escudo_path=extra.get("escudo", ""),
        institucion=extra.get("institucion", "INSTITUCION EDUCATIVA"),
        ugel=extra.get("ugel", ""),
        director=extra.get("director", ""),
    )
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    subtipo = extra.get("subtipo", "sesion").lower()
    numero  = extra.get("numero", "")
    periodo = extra.get("periodo", "")
    LH = 5

    # título del documento
    if subtipo == "sesion":
        doc_label = "SESION DE APRENDIZAJE"
        if numero:
            doc_label += f"  -  N° {numero}"
        if periodo:
            doc_label += f"  -  {periodo} BIMESTRE"
    else:
        doc_label = title.upper()

    pdf.set_font("Helvetica", style="B", size=13)
    pdf.cell(0, 8, _sanitize(doc_label), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # datos informativos
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 7, "I.  DATOS INFORMATIVOS", new_x="LMARGIN", new_y="NEXT")

    grado_val = " ".join(filter(None, [extra.get("grado", ""), extra.get("nivel", "")]))
    _salon = extra.get("salon", extra.get("seccion", ""))
    if _salon:
        grado_val += f"\n\"Secc. {_salon}\""

    _datos_row(pdf, [
        ("AREA",             12, extra.get("curso",   extra.get("area",  "")),   26),
        ("DOCENTE",          22, extra.get("docente", extra.get("profesor", "")), 36),
        ("GRADO Y\nSECCION", 22, grado_val,                                       24),
        ("FECHA",            12, extra.get("fecha", _date.today().strftime("%d/%m/%Y")), 26),
    ])
    pdf.ln(3)

    # título de la sesión
    titulo_sesion = parsed.get("titulo", extra.get("tema", title))
    pdf.set_font("Helvetica", style="B", size=10)
    lbl2 = "II.  TITULO DE LA SESION:  "
    pdf.cell(pdf.get_string_width(lbl2), 6, _sanitize(lbl2))
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.multi_cell(0, 6, _sanitize(f'"{titulo_sesion}"'), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # propósito
    proposito = parsed.get("proposito", "")
    pdf.set_font("Helvetica", style="B", size=10)
    lbl3 = "III.  PROPOSITO DE LA SESION:  "
    pdf.cell(pdf.get_string_width(lbl3), 6, _sanitize(lbl3))
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.multi_cell(0, 6, _sanitize(f'"{proposito}"'), align="J", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # tabla de competencias
    competencia = parsed.get("competencia", "")
    capacidad   = parsed.get("capacidad",   "")
    desempeno   = parsed.get("desempeno",   "")
    evidencias  = parsed.get("evidencias",  "")
    instrumento = parsed.get("instrumento", "")

    COMP_COLS = [
        ("COMPETENCIA",                 38),
        ("CAPACIDAD",                   33),
        ("DESEMPENO PRECISADO",         43),
        ("EVIDENCIAS DE APRENDIZAJE",   36),
        ("INSTRUMENTO DE EVALUACION",   30),
    ]
    HDR_H = 14

    # header de competencias
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
        pdf.set_xy(x, y_ch + (HDR_H - n * LH) / 2)
        pdf.multi_cell(w, LH, _sanitize(hdr), border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        x += w
    pdf.set_xy(pdf.l_margin, y_ch + HDR_H)

    # fila de datos
    vals = [competencia, capacidad, desempeno, evidencias, instrumento]
    data_cells = [(v, c[1], "I") for v, c in zip(vals, COMP_COLS)]
    _mc_row(pdf, data_cells, line_h=LH, align="C")
    pdf.ln(3)

    # secuencia de aprendizaje
    ACT_W  = 130
    MAT_W  = 37
    TMP_W  = 13
    FULL_W = ACT_W + MAT_W + TMP_W
    HDR_SEQ = 9

    _min_seq = 7 + HDR_SEQ + 4 * LH
    if pdf.h - pdf.b_margin - pdf.get_y() < _min_seq:
        pdf.add_page()

    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 7, "IV.  SECUENCIA DE APRENDIZAJE", new_x="LMARGIN", new_y="NEXT")
    y_sh = pdf.get_y()
    pdf.set_fill_color(210, 210, 210)
    pdf.rect(pdf.l_margin,                  y_sh, ACT_W,  HDR_SEQ, style="FD")
    pdf.rect(pdf.l_margin + ACT_W,          y_sh, MAT_W,  HDR_SEQ, style="FD")
    pdf.rect(pdf.l_margin + ACT_W + MAT_W,  y_sh, TMP_W,  HDR_SEQ, style="FD")

    pdf.set_font("Helvetica", style="B", size=9)
    pdf.set_xy(pdf.l_margin, y_sh + 1)
    pdf.cell(ACT_W, HDR_SEQ - 2,
             _sanitize("ACTIVIDADES Y ESTRATEGIAS DE APRENDIZAJE"), border=0, align="C")
    pdf.set_font("Helvetica", style="B", size=7)
    pdf.set_xy(pdf.l_margin + ACT_W, y_sh + 1)
    pdf.cell(MAT_W, HDR_SEQ - 2, _sanitize("MATERIALES/RECURSOS"), border=0, align="C")
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

        # normalizar tiempo
        if tiempo and not any(c in tiempo for c in ("'", "m", "’")):
            tiempo = tiempo + "'"

        # pre-calcular alturas
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

        # anti-huérfano
        remaining = pdf.h - pdf.b_margin - pdf.get_y()
        if remaining < 4 * LH:
            pdf.add_page()
        remaining = pdf.h - pdf.b_margin - pdf.get_y()

        if row_h <= remaining:
            # bloque completo en esta página
            y0 = pdf.get_y()
            pdf.rect(x_acts, y0, ACT_W, row_h)
            pdf.rect(x_mats, y0, MAT_W, row_h)
            pdf.rect(x_tmp,  y0, TMP_W, row_h)

            pdf.set_xy(x_acts, y0 + 1)
            pdf.set_font("Helvetica", style="BI", size=9)
            pdf.cell(ACT_W, LH, _sanitize(phase_label + ":"), border=0,
                     new_x="LMARGIN", new_y="NEXT")

            for _raw in actividades.split("\n"):
                _line = _raw.strip()
                if not _line:
                    pdf.set_font("Helvetica", size=9)
                    pdf.cell(ACT_W, 2, "", new_x="LMARGIN", new_y="NEXT")
                    continue
                pdf.set_font("Helvetica", style="B" if _is_subtitle(_line) else "", size=9)
                pdf.multi_cell(ACT_W, LH, _sanitize(_line), border=0,
                               new_x="LMARGIN", new_y="NEXT")

            if mat_text:
                pdf.set_font("Helvetica", style="I", size=8)
                pdf.set_xy(x_mats, y0 + 1)
                pdf.multi_cell(MAT_W, LH, _sanitize(mat_text), border=0,
                               new_x="LMARGIN", new_y="NEXT")

            # tiempo centrado verticalmente
            pdf.set_font("Helvetica", style="B", size=9)
            pdf.set_xy(x_tmp, y0 + (row_h - LH) / 2)
            pdf.cell(TMP_W, LH, _sanitize(tiempo), border=0, align="C",
                     new_x="LMARGIN", new_y="NEXT")

            pdf.set_xy(x_acts, y0 + row_h)

        else:
            # actividades largas: fluyen a páginas siguientes
            y0 = pdf.get_y()
            remaining_b = pdf.h - pdf.b_margin - y0

            pdf.rect(x_mats, y0, MAT_W, remaining_b)
            pdf.rect(x_tmp,  y0, TMP_W, remaining_b)

            if mat_text:
                pdf.set_auto_page_break(False)
                pdf.set_font("Helvetica", style="I", size=8)
                pdf.set_xy(x_mats, y0 + 1)
                pdf.multi_cell(MAT_W, LH, _sanitize(mat_text), border=0,
                               new_x="LMARGIN", new_y="NEXT")
                pdf.set_auto_page_break(True, margin=15)

            pdf.set_font("Helvetica", style="B", size=9)
            pdf.set_xy(x_tmp, y0 + remaining_b / 2 - LH / 2)
            pdf.cell(TMP_W, LH, _sanitize(tiempo), border=0, align="C",
                     new_x="LMARGIN", new_y="NEXT")

            pdf.set_xy(x_acts, y0)
            pdf.set_font("Helvetica", style="BI", size=9)
            pdf.multi_cell(ACT_W, LH, _sanitize(phase_label + ":"), border="LR",
                           new_x="LMARGIN", new_y="NEXT")
            for _raw in actividades.split("\n"):
                _line = _raw.strip()
                if not _line:
                    pdf.set_font("Helvetica", size=9)
                    pdf.cell(ACT_W, 2, "", border="LR", new_x="LMARGIN", new_y="NEXT")
                    continue
                pdf.set_font("Helvetica", style="B" if _is_subtitle(_line) else "", size=9)
                pdf.multi_cell(ACT_W, LH, _sanitize(_line), border="LR",
                               new_x="LMARGIN", new_y="NEXT")

            # línea de cierre
            y_close = pdf.get_y()
            pdf.set_draw_color(0, 0, 0)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, y_close, pdf.l_margin + FULL_W, y_close)

    return bytes(pdf.output())
