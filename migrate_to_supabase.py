"""
Migration script: Create initial tables in Supabase/PostgreSQL.
Run this once to set up the database schema.
"""
import sys, os
os.chdir(r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')
sys.path.insert(0, r'd:\DiffSense-AI\DiffSense-AI\aidiffchecker')

from sqlalchemy import create_engine, text
from backend.config import config
from backend.models import Base

DB_URL = config.ADMIN_DB_URL
print(f"Connecting to: {DB_URL[:30]}...")

engine = create_engine(DB_URL, pool_pre_ping=True)

# Create all tables defined in models.py (users, reference_pdfs)
print("Creating tables from ORM models...")
Base.metadata.create_all(engine)
print("ORM tables created.")

# Verify tables exist
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """))
    tables = [row[0] for row in result]
    print(f"Tables in database: {tables}")

# Insert default admin user if not exists
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

with engine.connect() as conn:
    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": "admin"}
    ).first()

    if existing:
        print("Admin user already exists.")
    else:
        hashed = pwd_context.hash("admin123")
        conn.execute(text("""
            INSERT INTO users (username, full_name, hashed_password, role)
            VALUES (:u, :fn, :hp, :r)
        """), {"u": "admin", "fn": "Administrator", "hp": hashed, "r": "admin"})
        conn.commit()
        print("Default admin user created (admin / admin123)")

print("\nMigration complete!")
