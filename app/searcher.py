import re

import config
from db import get_connection
from acl import is_table_allowed, TABLE_DENYLIST
from sanitizer import sanitize_context
from schema_loader import get_table_columns, get_fk_joins

ACCESS_DENIED = "__ACCESS_DENIED__"

# Maximo de filas permitidas por tabla (anti-volcado)
_MAX_ROWS_PER_TABLE = 100
_MAX_ROWS_PER_KEYWORD = 50

# Palabras que no deben usarse como filtros de busqueda
_STOP_WORDS = {
    "dime", "dame", "todos", "todas", "cuales", "cual", "lista", "muestra",
    "registros", "datos", "tabla", "tablas", "tiene", "hay", "cuantos",
    "cuantas", "existe", "existen", "para", "como", "cuando", "donde",
    "quiero", "necesito", "puedes", "puede", "favor", "gracias", "este",
    "esta", "estos", "estas", "aqui", "alli", "muestrame", "listame",
    "busca", "buscar", "encuentro", "encuentra", "dando", "favor",
    "cuanto", "muchos", "algunos", "cada", "entre", "desde", "hasta",
}


def _extract_column_filter(question: str, columns: list[str]) -> tuple[str, str] | None:
    """
    Detecta patrones de filtro exacto en la pregunta natural.


    La columna se valida contra el schema real (nunca se inyecta user input).
    Devuelve (nombre_columna_real, valor) o None.
    """
    q = question.lower()
    cols_lower = {c.lower(): c for c in columns}

    # Patron 1: con/where/donde <col> [=:]? <val>
    m = re.search(r'\b(?:con|where|donde|igual a|es)\s+(\w+)\s*[=:]?\s*[\'"]?(\w+)[\'"]?', q)
    if m:
        col_candidate, val_candidate = m.group(1), m.group(2)
        if col_candidate in cols_lower and len(val_candidate) > 1:
            return (cols_lower[col_candidate], val_candidate)

    # Patron 2: <col> = <val> o <col>: <val>
    m = re.search(r'\b(\w+)\s*[=:]\s*[\'"]?(\w+)[\'"]?', q)
    if m:
        col_candidate, val_candidate = m.group(1), m.group(2)
        if col_candidate in cols_lower and len(val_candidate) > 1:
            return (cols_lower[col_candidate], val_candidate)

    return None


def _build_joined_query(
    table_name: str,
    columns: list[str],
    cursor,
    where_clause: str = "",
    where_params: list = [],
    limit: int = _MAX_ROWS_PER_TABLE,
) -> list[dict]:
    """
    Construye y ejecuta un SELECT con LEFT JOINs automaticos hacia tablas
    relacionadas por FK que tambien esten en ALLOWED_TABLES.
    Las columnas de tablas relacionadas se prefijan con el nombre de la tabla
    para evitar colisiones: persona__pernombre, persona__perapellido, etc.
    """
    fk_joins = get_fk_joins(table_name)

    # Columnas de la tabla principal con alias tabla__columna
    select_parts = [f'"{table_name}"."{c}" AS "{table_name}__{c}"' for c in columns]
    join_parts: list[str] = []
    joined_cols: dict[str, list[str]] = {}  # {alias: [col, ...]}

    for rel in fk_joins:
        target = rel["target_table"]
        src_col = rel["source_col"]
        tgt_col = rel["target_col"]
        target_cols = get_table_columns(target)
        if not target_cols:
            continue
        join_parts.append(
            f'LEFT JOIN "{target}" ON "{table_name}"."{src_col}" = "{target}"."{tgt_col}"'
        )
        for c in target_cols:
            select_parts.append(f'"{target}"."{c}" AS "{target}__{c}"')
        joined_cols[target] = target_cols

    col_sql = ", ".join(select_parts)
    join_sql = " ".join(join_parts)
    where_sql = f"WHERE {where_clause}" if where_clause else ""

    sql = f'SELECT {col_sql} FROM "{table_name}" {join_sql} {where_sql} LIMIT %s'
    cursor.execute(sql, (*where_params, limit))

    results = []
    for row in cursor.fetchall():
        # Reconstruir dict aplanado: {columna: valor} sin el prefijo de tabla
        # para que la IA lo lea naturalmente; pero incluimos la tabla de origen
        flat: dict = {}
        idx = 0
        for c in columns:
            flat[c] = row[idx]; idx += 1
        for target, tcols in joined_cols.items():
            for c in tcols:
                flat[f"{target}.{c}"] = row[idx]; idx += 1
        results.append({"tabla": table_name, "datos": flat})
    return results


def search_relevant_data(question: str, extra_params: dict | None = None) -> list[dict] | str:
    """
    Firewall entre la IA y la base de datos.

    Politica DEFAULT DENY:
    - Solo consulta tablas en ALLOWED_TABLES que NO esten en TABLE_DENYLIST.
    - Si extra_params.tablas viene en el request, usa solo esas tablas
      (intersectadas con ALLOWED_TABLES como techo de seguridad).
    - Limita filas para prevenir volcados masivos.
    - Sanitiza columnas sensibles antes de devolver.
    """
    # Tablas efectivas para este request
    # Si el cliente manda "tablas", se usan solo esas — siempre dentro de ALLOWED_TABLES
    if extra_params and extra_params.get("tablas"):
        requested = {t.strip().lower() for t in extra_params["tablas"] if t.strip()}
        effective_allowed = requested & config.ALLOWED_TABLES  # techo de seguridad
    else:
        effective_allowed = config.ALLOWED_TABLES

    words = {w.strip("?.,;:()[]{}'").lower() for w in question.split()}

    results = []
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Obtener todas las tablas del schema publico
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        all_tables = {row[0].lower() for row in cursor.fetchall()}

        tables_in_question = words & all_tables

        # Fuzzy: tambien probar sin 's' final (plural en espanol, ej: "configuras" -> "configura")
        for w in list(words):
            if w.endswith("s") and w[:-1] in all_tables:
                tables_in_question.add(w[:-1])

        # Aliases: si el usuario dice "alumno" pero la tabla real es "ist_alumno"
        # config.TABLE_ALIASES = {"alumno": "ist_alumno", ...}
        for w in list(words):
            # alias exacto
            real = config.TABLE_ALIASES.get(w)
            if real and real in all_tables:
                tables_in_question.add(real)
            # alias plural (sin 's')
            if w.endswith("s"):
                real = config.TABLE_ALIASES.get(w[:-1])
                if real and real in all_tables:
                    tables_in_question.add(real)

        # Descripciones: si el usuario dice "alumnos" y TABLE_DESCRIPTIONS tiene
        # ist_alumno -> {"alumno", "alumnos", "estudiante", ...}, matchea ist_alumno
        # Solo aplica a tablas que esten en effective_allowed
        for real_table, keywords in config.TABLE_DESCRIPTIONS.items():
            if real_table in all_tables and real_table in effective_allowed and words & keywords:
                tables_in_question.add(real_table)

        # DENYLIST CHECK: si menciona cualquier tabla prohibida -> denegar
        denylist_mentioned = tables_in_question & TABLE_DENYLIST
        if denylist_mentioned:
            return ACCESS_DENIED

        # ALLOWLIST CHECK: solo tablas en effective_allowed (ALLOWED_TABLES o subconjunto del cliente)
        matched_tables = {t for t in tables_in_question if t in effective_allowed and not (t in TABLE_DENYLIST)}

        # Si menciono tablas fuera de effective_allowed -> denegar
        unmatched = tables_in_question - matched_tables - TABLE_DENYLIST
        if unmatched:
            return ACCESS_DENIED

        if matched_tables:
            # Palabras clave utiles: no son nombres de tabla, no son stop words, len > 3
            extra_keywords = [
                w for w in words
                if w not in all_tables
                and w not in _STOP_WORDS
                and len(w) > 3
            ]

            for table_name in matched_tables:
                try:
                    # Obtener columnas de la tabla (nunca SELECT *)
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        ORDER BY ordinal_position
                    """, (table_name,))
                    columns = [row[0] for row in cursor.fetchall()]
                    if not columns:
                        continue

                    col_list = ", ".join(f'"{c}"' for c in columns)

                    if extra_keywords:
                        # Intentar detectar filtro exacto: "CON configcod INTRANET"
                        col_filter = _extract_column_filter(question, columns)
                        if col_filter:
                            col_name, val = col_filter
                            results.extend(_build_joined_query(
                                table_name, columns, cursor,
                                where_clause=f'LOWER("{col_name}") = %s',
                                where_params=[val.lower()],
                            ))
                        else:
                            # Fallback: buscar keywords con LIKE en columnas de texto
                            cursor.execute("""
                                SELECT column_name FROM information_schema.columns
                                WHERE table_schema = 'public' AND table_name = %s
                                  AND data_type IN ('text', 'character varying', 'varchar')
                            """, (table_name,))
                            text_cols = [row[0] for row in cursor.fetchall()]

                            if text_cols:
                                for keyword in extra_keywords:
                                    for col in text_cols:
                                        try:
                                            results.extend(_build_joined_query(
                                                table_name, columns, cursor,
                                                where_clause=f'LOWER("{table_name}"."{col}") LIKE %s',
                                                where_params=[f"%{keyword.lower()}%"],
                                                limit=_MAX_ROWS_PER_TABLE,
                                            ))
                                        except Exception:
                                            conn.rollback()
                            else:
                                results.extend(_build_joined_query(
                                    table_name, columns, cursor
                                ))
                    else:
                        # Sin keywords extra: listar tabla completa con JOINs
                        results.extend(_build_joined_query(
                            table_name, columns, cursor
                        ))

                except Exception:
                    conn.rollback()

        else:
            # Busqueda por palabras clave solo en tablas de la allowlist efectiva
            safe_tables = {t for t in all_tables if is_table_allowed(t)}
            if not safe_tables:
                return []

            allowed_list = ", ".join(f"'{t}'" for t in safe_tables)
            keywords = [w for w in words if len(w) > 3]
            if not keywords:
                return []

            cursor.execute(f"""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN ({allowed_list})
                  AND data_type IN ('text', 'character varying', 'varchar')
            """)
            text_columns = cursor.fetchall()

            for keyword in keywords:
                for table_name, column_name in text_columns:
                    try:
                        cursor.execute(
                            f'SELECT * FROM "{table_name}" WHERE LOWER("{column_name}") LIKE %s LIMIT %s',
                            (f"%{keyword}%", _MAX_ROWS_PER_KEYWORD)
                        )
                        rows = cursor.fetchall()
                        col_names = [desc[0] for desc in cursor.description]
                        for row in rows:
                            results.append({
                                "tabla": table_name,
                                "datos": dict(zip(col_names, row))
                            })
                    except Exception:
                        conn.rollback()
                        continue

    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    # Eliminar duplicados
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = str(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Sanitizar columnas sensibles antes de entregar al modelo de IA
    return sanitize_context(unique)
