"""
user_db.py  ─  Per-user dynamic table helpers
==============================================
Each user gets their own tables in the shared Supabase database:
    uploads_{role}_{username}       e.g.  uploads_student_alice
    comparisons_{role}_{username}   e.g.  comparisons_teacher_bob

DDL (CREATE/DROP TABLE) uses Supabase CLI (subprocess).
DML (INSERT/SELECT/DELETE) uses PostgREST via SupabaseDB.
"""

import subprocess
import os
import tempfile

from backend.db.supabase_client import db

# Path to supabase CLI
SUPABASE_CLI = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "supabase", "supabase.exe")
PROJECT_REF = "crzymgnpzbdkpsqpaywu"


def _uploads_table(username: str, role: str) -> str:
    return f"uploads_{role}_{username}"

def _comparisons_table(username: str, role: str) -> str:
    return f"comparisons_{role}_{username}"


# ──────────────────────────────────────────────────────────────────────────
# CLI HELPER (DDL)
# ──────────────────────────────────────────────────────────────────────────
def _cli_query(sql: str) -> str:
    """Execute SQL via supabase CLI using a temp file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False,
                                     encoding='utf-8') as f:
        f.write(sql)
        tmp_path = f.name
    try:
        cmd = [SUPABASE_CLI, "db", "query", "-f", tmp_path,
               "--linked", "--project-ref", PROJECT_REF]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                cwd=r"d:\DiffSense-AI\DiffSense-AI")
        if result.returncode != 0:
            print(f"[ERROR] CLI query failed: {result.stderr[:200]}")
        return result.stdout
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────────────
# CREATE / DROP PER-USER TABLES
# ──────────────────────────────────────────────────────────────────────────
def create_user_db(username: str, role: str):
    """Create per-user uploads and comparisons tables."""
    ut = _uploads_table(username, role)
    ct = _comparisons_table(username, role)
    print(f"[INFO] Creating tables '{ut}' and '{ct}' …")

    _cli_query(f"""
        CREATE TABLE IF NOT EXISTS {ut} (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            uploaded_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS {ct} (
            id SERIAL PRIMARY KEY,
            student_pdf VARCHAR(255),
            reference_pdf VARCHAR(255),
            result_pdf VARCHAR(255),
            similarity FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    print(f"[INFO] Tables '{ut}' and '{ct}' ready.")


def drop_user_db(username: str, role: str):
    """Drop per-user tables (used when deleting a user)."""
    ut = _uploads_table(username, role)
    ct = _comparisons_table(username, role)
    _cli_query(f"DROP TABLE IF EXISTS {ct}; DROP TABLE IF EXISTS {ut};")
    print(f"[INFO] Dropped tables for {role}_{username}")


# ──────────────────────────────────────────────────────────────────────────
# UPLOAD CRUD
# ──────────────────────────────────────────────────────────────────────────
def save_upload(username: str, role: str, filename: str, delete: bool = False):
    """Insert or delete a filename record in the user's uploads table."""
    table = _uploads_table(username, role)
    if delete:
        db.delete_upload(table, filename)
        print(f"[INFO] Deleted '{filename}' from '{table}'")
    else:
        db.insert_upload(table, filename)
        print(f"[INFO] Saved '{filename}' in '{table}'")


def get_uploads(username: str, role: str) -> list[str]:
    """Return list of filenames uploaded by this user."""
    table = _uploads_table(username, role)
    try:
        return db.list_uploads(table)
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────
# COMPARISON CRUD
# ──────────────────────────────────────────────────────────────────────────
def save_result(username: str, role: str, student_pdf: str,
                result_pdf: str, results: list):
    """Persist comparison rows to the user's comparisons table."""
    table = _comparisons_table(username, role)
    for r in results:
        db.insert_comparison(table, {
            "student_pdf":   student_pdf,
            "reference_pdf": r.get("reference", ""),
            "result_pdf":    result_pdf,
            "similarity":    r.get("similarity", 0.0),
        })
    print(f"[INFO] Saved {len(results)} comparison row(s) for '{username}'.")


def get_results(username: str, role: str) -> list[dict]:
    """Return all comparison rows for a user."""
    table = _comparisons_table(username, role)
    try:
        return db.list_comparisons(table)
    except Exception:
        return []
