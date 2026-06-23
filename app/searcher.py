from __future__ import annotations

import re

import config
from db import get_connection
from acl import is_table_allowed, TABLE_DENYLIST
from sanitizer import sanitize_context
from schema_loader import get_table_columns, get_fk_joins

ACCESS_DENIED = "__ACCESS_DENIED__"

# límite de filas por tabla
_MAX_ROWS_PER_TABLE = 100
_MAX_ROWS_PER_KEYWORD = 50

# palabras ignoradas como filtros de búsqueda
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
    q = question.lower()
    cols_lower = {c.lower(): c for c in columns}

    # patrón: con/where/donde <col> <val>
    m = re.search(r'\b(?:con|where|donde|igual a|es)\s+(\w+)\s*[=:]?\s*[\'"]?(\w+)[\'"]?', q)
    if m:
        col_candidate, val_candidate = m.group(1), m.group(2)
        if col_candidate in cols_lower and len(val_candidate) > 1:
            return (cols_lower[col_candidate], val_candidate)

    # patrón: <col> = <val>
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
    fk_joins = get_fk_joins(table_name)

    # columnas principales con alias tabla__col
    select_parts = [f'"{table_name}"."{c}" AS "{table_name}__{c}"' for c in columns]
    join_parts: list[str] = []
    joined_cols: dict[str, list[str]] = {}

    for rel in fk_joins:
        target = rel["target_table"]
        if target in joined_cols:
            continue
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
    # tablas efectivas para este request
    if extra_params and extra_params.get("tablas"):
        requested = {t.strip().lower() for t in extra_params["tablas"] if t.strip()}
        effective_allowed = requested & config.ALLOWED_TABLES
    else:
        effective_allowed = config.ALLOWED_TABLES

    # aliases: base del .env + overrides del cliente
    request_aliases = dict(config.TABLE_ALIASES)
    if extra_params and isinstance(extra_params.get("alias"), dict):
        for logical, real in extra_params["alias"].items():
            if isinstance(logical, str) and isinstance(real, str):
                real_lower = real.strip().lower()
                if real_lower in effective_allowed:
                    request_aliases[logical.strip().lower()] = real_lower

    words = {w.strip("?.,;:()[]{}'").lower() for w in question.split()}

    results = []
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # tablas del schema público
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        all_tables = {row[0].lower() for row in cursor.fetchall()}

        tables_in_question = words & all_tables

        # plural en español (sin 's')
        for w in list(words):
            if w.endswith("s") and w[:-1] in all_tables:
                tables_in_question.add(w[:-1])

        # aliases exactos y plurales
        for w in list(words):
            real = request_aliases.get(w)
            if real and real in all_tables:
                tables_in_question.add(real)
            if w.endswith("s"):
                real = request_aliases.get(w[:-1])
                if real and real in all_tables:
                    tables_in_question.add(real)

        # detección semántica por palabras clave de TABLE_DESCRIPTIONS
        for real_table, keywords in config.TABLE_DESCRIPTIONS.items():
            if real_table in all_tables and real_table in effective_allowed and words & keywords:
                tables_in_question.add(real_table)

        # denylist check
        if tables_in_question & TABLE_DENYLIST:
            return ACCESS_DENIED

        # allowlist check
        matched_tables = {t for t in tables_in_question if t in effective_allowed and t not in TABLE_DENYLIST}

        if tables_in_question - matched_tables - TABLE_DENYLIST:
            return ACCESS_DENIED

        if matched_tables:
            # keywords útiles: no son tablas, no son stop words, len > 3
            extra_keywords = [
                w for w in words
                if w not in all_tables and w not in _STOP_WORDS and len(w) > 3
            ]

            for table_name in matched_tables:
                try:
                    # columnas de la tabla
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        ORDER BY ordinal_position
                    """, (table_name,))
                    columns = [row[0] for row in cursor.fetchall()]
                    if not columns:
                        continue

                    rows_before = len(results)

                    if extra_keywords:
                        # filtro exacto por columna
                        col_filter = _extract_column_filter(question, columns)
                        if col_filter:
                            col_name, val = col_filter
                            results.extend(_build_joined_query(
                                table_name, columns, cursor,
                                where_clause=f'LOWER("{col_name}") = %s',
                                where_params=[val.lower()],
                            ))
                        else:
                            # búsqueda LIKE en columnas de texto
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
                                results.extend(_build_joined_query(table_name, columns, cursor))

                    # si no hubo resultados, query general sin filtro
                    if len(results) == rows_before:
                        results.extend(_build_joined_query(table_name, columns, cursor))

                except Exception:
                    conn.rollback()

        else:
            # búsqueda por keywords en tablas de la allowlist
            safe_tables = {t for t in all_tables if is_table_allowed(t)}
            if not safe_tables:
                return []

            keywords = [w for w in words if len(w) > 3]
            if not keywords:
                return []

            cursor.execute("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                  AND data_type IN ('text', 'character varying', 'varchar')
            """, (list(safe_tables),))
            text_columns = cursor.fetchall()

            for keyword in keywords:
                for table_name, column_name in text_columns:
                    try:
                        fallback_cols = get_table_columns(table_name)
                        if not fallback_cols:
                            continue
                        fallback_col_sql = ", ".join(f'"{c}"' for c in fallback_cols)
                        cursor.execute(
                            f'SELECT {fallback_col_sql} FROM "{table_name}" WHERE LOWER("{column_name}") LIKE %s LIMIT %s',
                            (f"%{keyword}%", _MAX_ROWS_PER_KEYWORD)
                        )
                        rows = cursor.fetchall()
                        for row in rows:
                            results.append({"tabla": table_name, "datos": dict(zip(fallback_cols, row))})
                    except Exception:
                        conn.rollback()
                        continue

    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    # eliminar duplicados
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = str(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return sanitize_context(unique)
