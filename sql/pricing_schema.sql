-- =====================================================
-- 요금제 관리 시스템 DB 스키마
-- =====================================================

-- 1. 기존 테이블 백업 (필요시)
-- CREATE TABLE plans_backup AS SELECT * FROM plans;
-- CREATE TABLE user_subscriptions_backup AS SELECT * FROM user_subscriptions;

-- =====================================================
-- 1) PLANS: 판매/제공 중인 요금제의 카탈로그
-- =====================================================
DROP TABLE IF EXISTS plans;
CREATE TABLE plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '요금제명 (예: Free, Pro, Enterprise)',
    display_name VARCHAR(100) NOT NULL COMMENT '화면 표시용 이름',
    description TEXT COMMENT '요금제 설명',
    plan_type ENUM('free', 'paid', 'enterprise') NOT NULL DEFAULT 'paid' COMMENT '요금제 유형',
    
    -- 가격 정보
    price DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '월 정기 요금 (원)',
    currency VARCHAR(3) DEFAULT 'KRW' COMMENT '통화 코드',
    billing_cycle ENUM('monthly', 'yearly') DEFAULT 'monthly' COMMENT '결제 주기',
    
    -- 사용량 제한
    monthly_request_limit INT DEFAULT NULL COMMENT '월 API 요청 제한 (NULL = 무제한)',
    concurrent_requests INT DEFAULT 10 COMMENT '동시 요청 제한',
    
    -- 기능 제한
    features JSON COMMENT '포함된 기능들 (JSON 형태)',
    rate_limit_per_minute INT DEFAULT 60 COMMENT '분당 요청 제한',
    
    -- 상태 관리
    is_active BOOLEAN DEFAULT TRUE COMMENT '판매 활성 상태',
    is_popular BOOLEAN DEFAULT FALSE COMMENT '인기 요금제 표시',
    sort_order INT DEFAULT 0 COMMENT '표시 순서',
    
    -- 메타데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_plan_type (plan_type),
    INDEX idx_active (is_active),
    INDEX idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='요금제 카탈로그';

-- =====================================================
-- 2) SUBSCRIPTIONS: 사용자/조직의 요금제 구독 정보
-- =====================================================
DROP TABLE IF EXISTS subscriptions;
CREATE TABLE subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '구독자 ID',
    plan_id INT NOT NULL COMMENT '요금제 ID',
    
    -- 구독 기간
    started_at TIMESTAMP NOT NULL COMMENT '구독 시작일',
    expires_at TIMESTAMP NULL COMMENT '구독 만료일 (NULL = 무제한)',
    cancelled_at TIMESTAMP NULL COMMENT '취소일',
    
    -- 구독 상태
    status ENUM('active', 'cancelled', 'expired', 'suspended') DEFAULT 'active' COMMENT '구독 상태',
    
    -- 결제 정보
    amount DECIMAL(10,2) NOT NULL COMMENT '실제 결제 금액',
    currency VARCHAR(3) DEFAULT 'KRW',
    payment_method ENUM('card', 'bank', 'manual', 'free') DEFAULT 'card' COMMENT '결제 수단',
    
    -- 사용량 추적
    current_usage INT DEFAULT 0 COMMENT '현재 월 사용량',
    last_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '사용량 마지막 리셋일',
    
    -- 메타데이터
    notes TEXT COMMENT '관리자 메모',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 외래키 제약
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE RESTRICT,
    
    -- 인덱스
    INDEX idx_user_id (user_id),
    INDEX idx_plan_id (plan_id),
    INDEX idx_status (status),
    INDEX idx_expires (expires_at),
    UNIQUE KEY uk_user_active (user_id, status) -- 사용자당 하나의 활성 구독만
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='사용자 구독 정보';

-- =====================================================
-- 3) INVOICES: 청구서/영수증 기록
-- =====================================================
DROP TABLE IF EXISTS invoices;
CREATE TABLE invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subscription_id INT NOT NULL COMMENT '구독 ID',
    user_id INT NOT NULL COMMENT '사용자 ID',
    
    -- 청구서 정보
    invoice_number VARCHAR(50) UNIQUE NOT NULL COMMENT '청구서 번호',
    invoice_date DATE NOT NULL COMMENT '청구일',
    due_date DATE NOT NULL COMMENT '결제 기한',
    
    -- 금액 정보
    subtotal DECIMAL(10,2) NOT NULL COMMENT '세전 금액',
    tax_amount DECIMAL(10,2) DEFAULT 0.00 COMMENT '세금',
    total_amount DECIMAL(10,2) NOT NULL COMMENT '총 금액',
    currency VARCHAR(3) DEFAULT 'KRW',
    
    -- 청구 내역
    billing_period_start DATE NOT NULL COMMENT '청구 기간 시작',
    billing_period_end DATE NOT NULL COMMENT '청구 기간 종료',
    description TEXT COMMENT '청구 내역 설명',
    
    -- 상태
    status ENUM('draft', 'sent', 'paid', 'overdue', 'cancelled') DEFAULT 'draft' COMMENT '청구서 상태',
    paid_at TIMESTAMP NULL COMMENT '결제 완료일',
    
    -- 메타데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 외래키 제약
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    -- 인덱스
    INDEX idx_subscription_id (subscription_id),
    INDEX idx_user_id (user_id),
    INDEX idx_invoice_date (invoice_date),
    INDEX idx_status (status),
    INDEX idx_due_date (due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='청구서 관리';

-- =====================================================
-- 4) PAYMENTS: 실제 결제 기록
-- =====================================================
DROP TABLE IF EXISTS payments;
CREATE TABLE payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id INT NULL COMMENT '연관 청구서 ID (NULL 가능)',
    subscription_id INT NOT NULL COMMENT '구독 ID',
    user_id INT NOT NULL COMMENT '사용자 ID',
    
    -- 결제 정보
    payment_id VARCHAR(100) UNIQUE NOT NULL COMMENT '결제 고유 ID (PG사 제공)',
    amount DECIMAL(10,2) NOT NULL COMMENT '결제 금액',
    currency VARCHAR(3) DEFAULT 'KRW',
    
    -- 결제 수단
    payment_method ENUM('card', 'bank', 'kakao_pay', 'manual') NOT NULL COMMENT '결제 수단',
    payment_gateway VARCHAR(50) COMMENT 'PG사 (예: toss, kakao)',
    
    -- 결제 상태
    status ENUM('pending', 'completed', 'failed', 'cancelled', 'refunded') DEFAULT 'pending' COMMENT '결제 상태',
    
    -- 결제 일시
    processed_at TIMESTAMP NULL COMMENT '결제 처리 시간',
    failed_reason TEXT COMMENT '실패 사유',
    
    -- PG사 응답 데이터
    gateway_response JSON COMMENT 'PG사 응답 원본 (JSON)',
    
    -- 메타데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 외래키 제약
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    -- 인덱스
    INDEX idx_invoice_id (invoice_id),
    INDEX idx_subscription_id (subscription_id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_processed_at (processed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='결제 기록';

-- =====================================================
-- 5) USAGE_LOGS: API 사용량 추적 (선택적)
-- =====================================================
DROP TABLE IF EXISTS usage_logs;
CREATE TABLE usage_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '사용자 ID',
    subscription_id INT NULL COMMENT '구독 ID',
    
    -- API 호출 정보
    api_endpoint VARCHAR(200) NOT NULL COMMENT 'API 엔드포인트',
    request_method ENUM('GET', 'POST', 'PUT', 'DELETE') NOT NULL COMMENT 'HTTP 메소드',
    
    -- 사용량 정보
    tokens_consumed INT DEFAULT 1 COMMENT '소비된 토큰 수',
    response_time_ms INT COMMENT '응답 시간 (밀리초)',
    status_code INT COMMENT 'HTTP 응답 코드',
    
    -- 메타데이터
    user_ip VARCHAR(45) COMMENT '사용자 IP',
    user_agent TEXT COMMENT 'User Agent',
    request_id VARCHAR(100) COMMENT '요청 추적 ID',
    
    -- 시간 정보
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '로그 생성 시간',
    
    -- 외래키 제약
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL,
    
    -- 인덱스
    INDEX idx_user_id (user_id),
    INDEX idx_subscription_id (subscription_id),
    INDEX idx_logged_at (logged_at),
    INDEX idx_api_endpoint (api_endpoint),
    INDEX idx_status_code (status_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='API 사용량 로그';

-- =====================================================
-- 6) USAGE_SUMMARIES: 월별 사용량 집계 (성능 최적화용)
-- =====================================================
DROP TABLE IF EXISTS usage_summaries;
CREATE TABLE usage_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '사용자 ID',
    subscription_id INT NULL COMMENT '구독 ID',
    
    -- 집계 기간
    year INT NOT NULL COMMENT '연도',
    month INT NOT NULL COMMENT '월',
    
    -- 사용량 집계
    total_requests INT DEFAULT 0 COMMENT '총 요청 수',
    total_tokens INT DEFAULT 0 COMMENT '총 토큰 사용량',
    success_requests INT DEFAULT 0 COMMENT '성공 요청 수',
    failed_requests INT DEFAULT 0 COMMENT '실패 요청 수',
    
    -- 성능 지표
    avg_response_time_ms DECIMAL(8,2) COMMENT '평균 응답 시간',
    
    -- 메타데이터
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 외래키 제약
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL,
    
    -- 인덱스
    UNIQUE KEY uk_user_month (user_id, year, month),
    INDEX idx_subscription_id (subscription_id),
    INDEX idx_year_month (year, month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='월별 사용량 집계';
