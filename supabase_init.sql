-- DiffSense-AI Initial Schema for Supabase/PostgreSQL
-- Run once to set up the database

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    hashed_password VARCHAR(255),
    role VARCHAR(20) NOT NULL,
    disabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Reference PDFs table
CREATE TABLE IF NOT EXISTS reference_pdfs (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    uploaded_by INTEGER REFERENCES users(id),
    uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Insert default admin user if not exists
INSERT INTO users (username, full_name, hashed_password, role)
SELECT 'admin', 'Administrator', '$2b$12$LJ3m4ys3Lk0TSwMcMGQcOeOQbPzE0FkEyXBXxPyWY7tBfYJfHixOa', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');
