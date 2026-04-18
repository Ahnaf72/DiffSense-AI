-- =============================================================================
-- DiffSense-AI MySQL Initialization Script
-- Creates admin_db database and users table
-- =============================================================================

-- Create database if not exists (should already exist from MYSQL_DATABASE env)
CREATE DATABASE IF NOT EXISTS admin_db;
USE admin_db;

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'teacher', 'student') NOT NULL DEFAULT 'student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default admin user (password: admin123)
-- IMPORTANT: Change this password after first login!
-- Password hash generated with: passlib.hash.bcrypt.hash("admin123")
INSERT IGNORE INTO users (username, password_hash, role) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VttYxKDWJvO/Aq', 'admin');

-- Grant privileges (for non-root user if configured)
-- Note: Root user already has all privileges
