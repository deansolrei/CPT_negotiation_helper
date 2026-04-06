"""
database.py
-----------
Manages the PostgreSQL connection pool for the Solrei CPT Negotiation app.
Uses psycopg2 with a simple connection-per-request pattern.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/solrei_cpt")


def get_connection():
    """Open a new database connection."""
    return psycopg2.connect(DATABASE_URL)


@contextmanager
def get_db():
    """
    Context manager that yields a database cursor and handles
    commit/rollback automatically.

    Usage:
        with get_db() as cursor:
            cursor.execute("SELECT ...")
            rows = cursor.fetchall()
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
