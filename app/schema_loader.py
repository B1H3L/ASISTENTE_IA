import config
from db import get_connection

# cache columnas: {tabla: [col1, col2, ...]}
_schema_cache: dict[str, list[str]] = {}

# cache fks: {tabla: [{source_col, target_table, target_col}]}
_fk_cache: dict[str, list[dict]] = {}


def load_schema() -> None:
    global _schema_cache
    if not config.ALLOWED_TABLES:
        return
    try:
        conn = get_connection()
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(config.ALLOWED_TABLES))
        cur.execute(
            f"""
            SELECT LOWER(table_name), column_name
            FROM information_schema.columns
            WHERE LOWER(table_name) IN ({placeholders})
            ORDER BY table_name, ordinal_position
            """,
            list(config.ALLOWED_TABLES),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        schema: dict[str, list[str]] = {}
        for table, col in rows:
            schema.setdefault(table, []).append(col)
        _schema_cache = schema
        total_cols = sum(len(v) for v in schema.values())
        print(f"[schema_loader] {len(schema)} tabla(s), {total_cols} columna(s).")
    except Exception as e:
        print(f"[schema_loader] Error cargando esquema: {e}")


def load_foreign_keys() -> None:
    global _fk_cache
    if not config.ALLOWED_TABLES:
        return
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                LOWER(kcu.table_name)   AS source_table,
                kcu.column_name         AS source_col,
                LOWER(ccu.table_name)   AS target_table,
                ccu.column_name         AS target_col
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.referential_constraints rc
                ON kcu.constraint_name = rc.constraint_name
                AND kcu.constraint_schema = rc.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
                ON rc.unique_constraint_name = ccu.constraint_name
                AND rc.unique_constraint_schema = ccu.constraint_schema
            WHERE kcu.table_schema = 'public'
            ORDER BY
                CASE WHEN kcu.column_name = ccu.column_name THEN 0 ELSE 1 END,
                kcu.table_name, kcu.column_name
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        fk: dict[str, list[dict]] = {}
        for source_table, source_col, target_table, target_col in rows:
            # solo si ambas tablas están en ALLOWED_TABLES
            if source_table in config.ALLOWED_TABLES and target_table in config.ALLOWED_TABLES:
                fk.setdefault(source_table, []).append({
                    "source_col": source_col,
                    "target_table": target_table,
                    "target_col": target_col,
                })
        _fk_cache = fk
        total_fks = sum(len(v) for v in fk.values())
        print(f"[schema_loader] {total_fks} FK(s) entre tablas permitidas.")
    except Exception as e:
        print(f"[schema_loader] Error cargando FKs: {e}")


def get_schema_text() -> str:
    if not _schema_cache:
        return ""
    lines = []
    for table, cols in _schema_cache.items():
        desc = config.TABLE_DESCRIPTIONS.get(table)
        desc_text = f" [{', '.join(sorted(desc))}]" if desc else ""
        lines.append(f"Tabla '{table}'{desc_text}: columnas [{', '.join(cols)}]")
    if _fk_cache:
        lines.append("\nRelaciones entre tablas:")
        for src, rels in _fk_cache.items():
            for r in rels:
                lines.append(f"  {src}.{r['source_col']} -> {r['target_table']}.{r['target_col']}")
    return "\n".join(lines)


def get_table_columns(table: str) -> list[str]:
    return _schema_cache.get(table.lower(), [])


def get_fk_joins(table: str) -> list[dict]:
    return _fk_cache.get(table.lower(), [])


def reload_schema() -> None:
    global _schema_cache, _fk_cache
    _schema_cache = {}
    _fk_cache = {}
    load_schema()
    load_foreign_keys()
