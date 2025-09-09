-- API 키 테이블 생성
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'API 키 ID (공개 키)',
    secret_key VARCHAR(128) NOT NULL COMMENT '비밀 키',
    user_id INT NOT NULL COMMENT '사용자 ID',
    name VARCHAR(255) NOT NULL COMMENT 'API 키 이름',
    description TEXT COMMENT 'API 키 설명',
    allowed_domains TEXT COMMENT '허용된 도메인 목록 (JSON 배열)',
    is_active BOOLEAN DEFAULT TRUE COMMENT '활성화 여부',
    rate_limit_per_minute INT DEFAULT 60 COMMENT '분당 요청 제한',
    rate_limit_per_day INT DEFAULT 1000 COMMENT '일당 요청 제한',
    usage_count INT DEFAULT 0 COMMENT '사용 횟수',
    last_used_at TIMESTAMP NULL COMMENT '마지막 사용 시간',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시간',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시간',
    
    INDEX idx_key_id (key_id),
    INDEX idx_user_id (user_id),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API 키 관리';
