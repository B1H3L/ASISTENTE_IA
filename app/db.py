import psycopg2
import config


def get_connection():
    """Devuelve una conexión activa a PostgreSQL."""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    return conn


def check_connection():
    """Verifica que la conexión a PostgreSQL funciona correctamente."""
    try:
        conn = get_connection()
        conn.close()
        return True, "Conexión a PostgreSQL exitosa"
    except Exception as e:
        return False, f"Error al conectar a PostgreSQL: {e}"


if __name__ == "__main__":
    success, message = check_connection()
    print(message)
