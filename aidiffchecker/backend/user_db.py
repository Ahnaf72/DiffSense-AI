"""
user_db.py  ─  Per-user dynamic database helpers (Supabase REST API)
=====================================================================
Each user (teacher or student) gets their own tables in the SAME database:
    uploads_{role}_{username}       e.g.  uploads_student_alice
    comparisons_{role}_{username}   e.g.  comparisons_teacher_bob

Uses Supabase CLI (supabase db query) for DDL operations and
PostgREST API for DML operations, bypassing the IPv6-only direct
connection issue.
"""

import subprocess
import os
import httpx

from backend.config import config

# Supabase REST API configuration
SUPABASE_URL = config.SUPABASE_URL
SUPABASE_SERVICE_KEY = config.SUPABASE_SERVICE_KEY

# Path to supabase CLI
SUPABASE_CLI = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "supabase", "supabase.exe")
PROJECT_REF = "crzymgnpzbdkpsqpaywu"


def _uploads_table_name(username: str, role: str) -> str:
    return f"uploads_{role}_{username}"

def _comparisons_table_name(username: str, role: str) -> str:
    return f"comparisons_{role}_{username}"


# ──────────────────────────────────────────────────────────────────────────
# SUPABASE CLI HELPER (for DDL — CREATE/DROP TABLE)
# ──────────────────────────────────────────────────────────────────────────
def _cli_query(sql: str) -> str:
    """Execute SQL via supabase CLI using a temp file (works around IPv6 issue)."""
    import tempfile
    # Write SQL to a temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write(sql)
        tmp_path = f.name

    try:
        cmd = [SUPABASE_CLI, "db", "query", "-f", tmp_path, "--linked", "--project-ref", PROJECT_REF]
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
# REST API HELPER (for DML — INSERT/SELECT/DELETE)
# ──────────────────────────────────────────────────────────────────────────
_client = httpx.Client(timeout=30.0)
_headers = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _rest_request(method: str, table: str, *, params: dict = None,
                  json_data: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = _client.request(method, url, headers=_headers,
                        params=params, json=json_data)
    if r.status_code == 204:
        return None
    if r.status_code >= 400:
        print(f"[ERROR] REST {method} {table}: {r.status_code} {r.text[:200]}")
        r.raise_for_status()
    return r.json()


# ──────────────────────────────────────────────────────────────────────────
# CREATE PER-USER TABLES
# ──────────────────────────────────────────────────────────────────────────
def create_user_db(username: str, role: str):
    """
    Creates per-user tables in the same PostgreSQL database:
        uploads_{role}_{username}
        comparisons_{role}_{username}

    Uses supabase CLI for DDL since PostgREST doesn't support CREATE TABLE.
    """
    uploads_tbl = _uploads_table_name(username, role)
    comps_tbl   = _comparisons_table_name(username, role)

    print(f"[INFO] Ensuring tables '{uploads_tbl}' and '{comps_tbl}' exist …")

    _cli_query(f"""
        CREATE TABLE IF NOT EXISTS {uploads_tbl} (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            uploaded_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS {comps_tbl} (
            id SERIAL PRIMARY KEY,
            student_pdf VARCHAR(255),
            reference_pdf VARCHAR(255),
            result_pdf VARCHAR(255),
            similarity FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    print(f"[INFO] Tables '{uploads_tbl}' and '{comps_tbl}' ready.")


def drop_user_db(username: str, role: str):
    """Drop per-user tables (used when deleting a user)."""
    uploads_tbl = _uploads_table_name(username, role)
    comps_tbl   = _comparisons_table_name(username, role)

    _cli_query(f"DROP TABLE IF EXISTS {comps_tbl}; DROP TABLE IF EXISTS {uploads_tbl};")
    print(f"[INFO] Dropped tables for {role}_{username}")


# ──────────────────────────────────────────────────────────────────────────
# SAVE / DELETE UPLOAD RECORD
# ──────────────────────────────────────────────────────────────────────────
def save_upload(username: str, role: str, filename: str, delete: bool = False):
    """Insert or delete a filename record in the user's uploads table."""
    uploads_tbl = _uploads_table_name(username, role)

    if delete:
        _rest_request("DELETE", uploads_tbl,
                       params={"filename": f"eq.{filename}"})
        print(f"[INFO] Deleted '{filename}' from '{uploads_tbl}'")
    else:
        _rest_request("POST", uploads_tbl,
                       json_data={"filename": filename})
        print(f"[INFO] Saved '{filename}' in '{uploads_tbl}'")


# ──────────────────────────────────────────────────────────────────────────
# SAVE COMPARISON RESULT
# ──────────────────────────────────────────────────────────────────────────
def save_result(
    username:        str,
    role:            str,
    student_pdf:     str,
    result_pdf:      str,
    results:         list,   # list of {reference, similarity, …}
):
    """Persist one row per reference comparison to the user's comparisons table."""
    comps_tbl = _comparisons_table_name(username, role)

    for r in results:
        _rest_request("POST", comps_tbl, json_data={
            "student_pdf":   student_pdf,
            "reference_pdf": r.get("reference", ""),
            "result_pdf":    result_pdf,
            "similarity":    r.get("similarity", 0.0),
        })
    print(f"[INFO] Saved {len(results)} comparison row(s) for '{username}'.")


# ──────────────────────────────────────────────────────────────────────────
# GET RESULTS FOR A USER
# ──────────────────────────────────────────────────────────────────────────
def get_results(username: str, role: str) -> list[dict]:
    """Return all comparison rows for a user."""
    comps_tbl = _comparisons_table_name(username, role)

    try:
        rows = _rest_request("GET", comps_tbl, params={
            "select": "student_pdf,reference_pdf,result_pdf,similarity,created_at",
            "order": "created_at.desc",
        })
        return rows if rows else []
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────
# GET UPLOADS FOR A USER
# ──────────────────────────────────────────────────────────────────────────
def get_uploads(username: str, role: str) -> list[str]:
    """Return list of filenames uploaded by this user."""
    uploads_tbl = _uploads_table_name(username, role)

    try:
        rows = _rest_request("GET", uploads_tbl, params={
            "select": "filename",
            "order": "uploaded_at.desc",
        })
        return [row["filename"] for row in (rows or [])]
    except Exception:
        return []