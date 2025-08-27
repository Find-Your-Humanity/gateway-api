-- API 키 테이블 생성
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_id VARCHAR(50) UNIQUE NOT NULL,
    secret_key VARCHAR(255) NOT NULL,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    last_used_at TIMESTAMP NULL,
    usage_count INT DEFAULT 0,
    allowed_origins TEXT, -- JSON 형태로 저장
    rate_limit_per_minute INT DEFAULT 100,
    rate_limit_per_day INT DEFAULT 10000,
    INDEX idx_user_id (user_id),
    INDEX idx_key_id (key_id),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
