-- ═══════════════════════════════════════════════════════════════════
-- DiffSense AI — PostgreSQL Schema (Supabase-compatible)
-- ═══════════════════════════════════════════════════════════════════

-- ── Extensions ──────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "vector";    -- pgvector: vector similarity search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- auto-generate UUIDs

-- ═══════════════════════════════════════════════════════════════════
-- 1. users — App-level user accounts & roles
-- ═══════════════════════════════════════════════════════════════════
-- Stores every registered user with hashed credentials and role.
-- Roles: admin, user — used for access control throughout the app.

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    TEXT    NOT NULL UNIQUE,
    password_hash TEXT  NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'user'
                        CHECK (role IN ('admin', 'user')),
    full_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_role     ON users (role);

-- ═══════════════════════════════════════════════════════════════════
-- 2. documents — Uploaded files (PDFs, docs, etc.)
-- ═══════════════════════════════════════════════════════════════════
-- Every document uploaded by a user. Tracks file metadata so the
-- raw file can be retrieved from Supabase Storage later.

CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,          -- Supabase Storage path
    file_size   BIGINT  NOT NULL DEFAULT 0,
    mime_type   TEXT    NOT NULL DEFAULT 'application/pdf',
    upload_status TEXT  NOT NULL DEFAULT 'pending'
                        CHECK (upload_status IN ('pending', 'processing', 'ready', 'failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_user_id ON documents (user_id);
CREATE INDEX idx_documents_status  ON documents (upload_status);

-- ═══════════════════════════════════════════════════════════════════
-- 3. reference_corpus — Reference documents for comparison
-- ═══════════════════════════════════════════════════════════════════
-- Admin-uploaded reference PDFs that form the "ground truth" corpus.
-- User documents are compared against these to detect matches.

CREATE TABLE IF NOT EXISTS reference_corpus (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title       TEXT    NOT NULL,
    filename    TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,          -- Supabase Storage path
    file_size   BIGINT  NOT NULL DEFAULT 0,
    uploaded_by UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ref_corpus_active ON reference_corpus (is_active);

-- ═══════════════════════════════════════════════════════════════════
-- 4. chunks — Text segments + embeddings for similarity search
-- ═══════════════════════════════════════════════════════════════════
-- Each document / reference is split into chunks. Every chunk stores
-- its text content AND a pre-computed embedding vector so that:
--   • Similarity search is instant (no re-embedding at query time)
--   • Embeddings survive restarts (offline reuse)
-- The vector dimension (1536) matches OpenAI text-embedding-3-small.
-- Adjust if using a different model.

CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID        REFERENCES documents(id) ON DELETE CASCADE,
    reference_id    UUID        REFERENCES reference_corpus(id) ON DELETE CASCADE,
    source_type     TEXT        NOT NULL CHECK (source_type IN ('upload', 'reference')),
    source_id       UUID        NOT NULL,   -- points to document_id or reference_id
    chunk_index     INT         NOT NULL,    -- 0-based position in the source
    content         TEXT        NOT NULL,
    token_count     INT         NOT NULL DEFAULT 0,
    embedding       vector(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Ensure a chunk belongs to exactly one source
    CONSTRAINT chk_source_type_id CHECK (
        (source_type = 'upload'    AND source_id = document_id) OR
        (source_type = 'reference' AND source_id = reference_id)
    ),
    -- No duplicate chunk positions within a source
    CONSTRAINT uq_chunk_source_pos UNIQUE (source_type, source_id, chunk_index)
);

-- Core similarity search index (IVFFlat — good for moderate corpora)
-- Switch to HNSW for >1M rows: USING hnsw (embedding vector_cosine_ops)
CREATE INDEX idx_chunks_embedding ON chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_chunks_source_type ON chunks (source_type, source_id);
CREATE INDEX idx_chunks_document_id ON chunks (document_id);
CREATE INDEX idx_chunks_reference_id ON chunks (reference_id);

-- ═══════════════════════════════════════════════════════════════════
-- 5. reports — Generated comparison / diff reports
-- ═══════════════════════════════════════════════════════════════════
-- A report is produced each time a user's document is compared
-- against the reference corpus. It aggregates all matches and
-- stores the final similarity percentage and summary.

CREATE TABLE IF NOT EXISTS reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id         UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    overall_score       FLOAT       NOT NULL DEFAULT 0,
    total_chunks        INT         NOT NULL DEFAULT 0,
    matched_chunks      INT         NOT NULL DEFAULT 0,
    status              TEXT        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    summary             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_user_id     ON reports (user_id);
CREATE INDEX idx_reports_document_id ON reports (document_id);
CREATE INDEX idx_reports_status      ON reports (status);

-- ═══════════════════════════════════════════════════════════════════
-- 6. matches — Detected similarity pairs between chunks
-- ═══════════════════════════════════════════════════════════════════
-- Pairs of (upload_chunk, reference_chunk) that exceeded the
-- similarity threshold. Stores the cosine distance so results
-- can be re-ranked / filtered without recomputing.

CREATE TABLE IF NOT EXISTS matches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    upload_chunk_id     UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    reference_chunk_id  UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    similarity_score    FLOAT NOT NULL CHECK (similarity_score BETWEEN 0 AND 1),
    report_id           UUID REFERENCES reports(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Prevent duplicate match pairs
    CONSTRAINT uq_match_pair UNIQUE (upload_chunk_id, reference_chunk_id)
);

CREATE INDEX idx_matches_upload_chunk    ON matches (upload_chunk_id);
CREATE INDEX idx_matches_reference_chunk ON matches (reference_chunk_id);
CREATE INDEX idx_matches_report_id       ON matches (report_id);
CREATE INDEX idx_matches_score           ON matches (similarity_score DESC);

-- ═══════════════════════════════════════════════════════════════════
-- Helper: updated_at trigger
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'updated_at'
          AND table_schema = 'public'
          AND table_name IN ('users', 'documents', 'reference_corpus', 'reports')
    LOOP
        EXECUTE format(
            'CREATE TRIGGER set_updated_at BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()',
            t
        );
    END LOOP;
END;
$$;

-- ═══════════════════════════════════════════════════════════════════
-- Seed: default admin user  (password: admin123 — bcrypt hash)
-- ═══════════════════════════════════════════════════════════════════
-- INSERT INTO users (username, password_hash, role, full_name)
-- VALUES ('admin', '$2b$12$...hashed...', 'admin', 'Administrator');
-- Run this manually after schema creation.
