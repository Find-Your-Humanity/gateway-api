-- 1단계: api_keys 테이블이 존재하는지 확인하고 생성
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    key_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'API 키 ID (공개 키)',
    secret_key VARCHAR(128) NOT NULL COMMENT '비밀 키',
    user_id INT NOT NULL COMMENT '사용자 ID',
    name VARCHAR(255) NOT NULL COMMENT 'API 키 이름',
    description TEXT COMMENT 'API 키 설명',
    allowed_origins TEXT COMMENT '허용된 도메인 목록 (JSON 배열)',
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

-- 2단계: api_keys 테이블에 allowed_origins 컬럼 추가
-- 컬럼이 이미 존재하는 경우 오류를 무시하고 진행
ALTER TABLE api_keys 
ADD COLUMN allowed_origins TEXT COMMENT '허용된 도메인 목록 (JSON 배열)';

-- 3단계: 캡차 토큰 테이블 생성
CREATE TABLE IF NOT EXISTS captcha_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    token_id VARCHAR(64) NOT NULL UNIQUE COMMENT '토큰 ID',
    api_key_id BIGINT UNSIGNED NOT NULL COMMENT 'API 키 ID',
    user_id INT NOT NULL COMMENT '사용자 ID',
    captcha_type VARCHAR(50) NOT NULL COMMENT '캡차 타입',
    challenge_data TEXT COMMENT '캡차 챌린지 데이터 (JSON)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시간',
    expires_at TIMESTAMP NOT NULL COMMENT '만료 시간',
    is_used BOOLEAN DEFAULT FALSE COMMENT '사용 여부',
    used_at TIMESTAMP NULL COMMENT '사용 시간',
    INDEX idx_token_id (token_id),
    INDEX idx_api_key_id (api_key_id),
    INDEX idx_expires_at (expires_at),
    INDEX idx_is_used (is_used),
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='캡차 토큰 관리';

-- 만료된 토큰 정리를 위한 이벤트 스케줄러 (선택사항)
-- SET GLOBAL event_scheduler = ON;
-- 
-- CREATE EVENT IF NOT EXISTS cleanup_expired_tokens
-- ON SCHEDULE EVERY 1 HOUR
-- DO
--   DELETE FROM captcha_tokens 
--   WHERE expires_at < NOW() OR (is_used = 1 AND used_at < DATE_SUB(NOW(), INTERVAL 24 HOUR));
