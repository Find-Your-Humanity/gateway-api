import os
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager

# 데이터베이스 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'captcha'),
    'charset': 'utf8mb4',
    'cursorclass': DictCursor,
    'autocommit': True
}

@contextmanager
def get_db_connection():
    """데이터베이스 연결 컨텍스트 매니저"""
    connection = None
    try:
        connection = pymysql.connect(**DB_CONFIG)
        yield connection
    except Exception as e:
        print(f"데이터베이스 연결 오류: {e}")
        raise
    finally:
        if connection:
            connection.close()

def test_connection() -> bool:
    """데이터베이스 연결 가능 여부를 반환"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
    except Exception as e:
        print(f"데이터베이스 연결 테스트 실패: {e}")
        return False

def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # 사용자 테이블 생성 (contact 포함)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    contact VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # 스키마 보정: contact 컬럼 누락 시 추가
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS contact VARCHAR(255) NULL")
            except Exception:
                # 일부 MySQL에서는 IF NOT EXISTS 미지원 → 존재 여부 체크 후 추가
                try:
                    cursor.execute("SHOW COLUMNS FROM users LIKE 'contact'")
                    col = cursor.fetchone()
                    if not col:
                        cursor.execute("ALTER TABLE users ADD COLUMN contact VARCHAR(255) NULL")
                except Exception as e:
                    print(f"스키마 보정(contact 추가) 실패: {e}")

            # 스키마 보정: is_verified 컬럼 누락 시 추가
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE")
            except Exception:
                try:
                    cursor.execute("SHOW COLUMNS FROM users LIKE 'is_verified'")
                    col = cursor.fetchone()
                    if not col:
                        cursor.execute("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE")
                except Exception as e:
                    print(f"스키마 보정(is_verified 추가) 실패: {e}")

            # 스키마 보정: Google OAuth 관련 컬럼 추가
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) NULL")
            except Exception:
                try:
                    cursor.execute("SHOW COLUMNS FROM users LIKE 'google_id'")
                    col = cursor.fetchone()
                    if not col:
                        cursor.execute("ALTER TABLE users ADD COLUMN google_id VARCHAR(255) NULL")
                except Exception as e:
                    print(f"스키마 보정(google_id 추가) 실패: {e}")

            try:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider ENUM('local', 'google') DEFAULT 'local'")
            except Exception:
                try:
                    cursor.execute("SHOW COLUMNS FROM users LIKE 'oauth_provider'")
                    col = cursor.fetchone()
                    if not col:
                        cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider ENUM('local', 'google') DEFAULT 'local'")
                except Exception as e:
                    print(f"스키마 보정(oauth_provider 추가) 실패: {e}")

            # Google ID 인덱스 추가
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_google_id ON users(google_id)")
            except Exception:
                try:
                    cursor.execute("SHOW INDEX FROM users WHERE Key_name = 'idx_google_id'")
                    if not cursor.fetchone():
                        cursor.execute("CREATE INDEX idx_google_id ON users(google_id)")
                except Exception as e:
                    print(f"Google ID 인덱스 생성 실패: {e}")

            # 사용자 세션 테이블 생성
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    token_hash VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # 비밀번호 재설정 토큰 테이블 (URL 토큰 방식)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    token_sha256 CHAR(64) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_expires (user_id, expires_at),
                    UNIQUE KEY uniq_token (token_sha256),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # 비밀번호 재설정 6자리 코드 테이블 (이메일 OTP 방식)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_codes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    code_sha256 CHAR(64) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_expires (user_id, expires_at),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # 회원가입 이메일 인증 코드 테이블
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verification_codes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    code_sha256 CHAR(64) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_email_expires (email, expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # ---- 일자별 요청 집계 테이블: request_statistics ----
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS request_statistics (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  date DATE NOT NULL,
                  total_requests INT NOT NULL DEFAULT 0,
                  success_count INT NOT NULL DEFAULT 0,
                  failure_count INT NOT NULL DEFAULT 0,
                  UNIQUE KEY uniq_date (date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # ---- 집계 테이블: error_stats_daily ----
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS error_stats_daily (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  date DATE NOT NULL,
                  status_code INT NOT NULL,
                  count INT NOT NULL DEFAULT 0,
                  UNIQUE KEY uniq_date_status (date, status_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # ---- 집계 테이블: endpoint_usage_daily ----
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS endpoint_usage_daily (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  date DATE NOT NULL,
                  endpoint VARCHAR(100) NOT NULL,
                  requests INT NOT NULL DEFAULT 0,
                  avg_ms INT NULL,
                  UNIQUE KEY uniq_date_endpoint (date, endpoint)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # ---- 요청 로그 테이블: request_logs ----
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NULL,
                    api_key VARCHAR(255) NULL,
                    path VARCHAR(500) NOT NULL,
                    method VARCHAR(10) NOT NULL,
                    status_code INT NOT NULL,
                    response_time INT NOT NULL,
                    user_agent TEXT NULL,
                    request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_api_key (api_key),
                    INDEX idx_request_time (request_time),
                    INDEX idx_status_code (status_code),
                    INDEX idx_path (path),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # ---- API 키 테이블: api_keys ----
            cursor.execute(
                """
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
                    allowed_origins TEXT,
                    rate_limit_per_minute INT DEFAULT 100,
                    rate_limit_per_day INT DEFAULT 10000,
                    INDEX idx_user_id (user_id),
                    INDEX idx_key_id (key_id),
                    INDEX idx_is_active (is_active),
                    INDEX idx_created_at (created_at),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

def create_tables():
    # plans 테이블을 먼저 생성 (사진의 기능들을 위해)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            request_limit INT NOT NULL DEFAULT 1000,
            description TEXT,
            features JSON,
            rate_limit_per_minute INT DEFAULT 30,
            is_active BOOLEAN DEFAULT TRUE,
            is_popular BOOLEAN DEFAULT FALSE,
            sort_order INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    
    # users 테이블에 plan_id 컬럼 추가 (plans 테이블 생성 후)
    cursor.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS plan_id INT DEFAULT 1
    """)
    
    # 외래키 제약 조건 추가 (별도로 처리)
    try:
        cursor.execute("""
            ALTER TABLE users 
            ADD CONSTRAINT fk_users_plan_id 
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        """)
    except Exception as e:
        print(f"외래키 제약 조건 추가 실패 (이미 존재할 수 있음): {e}")
    
    # user_subscriptions 테이블 확장
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            plan_id INT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            status ENUM('active', 'cancelled', 'expired') DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    
    # 사용량 추적을 위한 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_tracking (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            plan_id INT NOT NULL,
            date DATE NOT NULL,
            tokens_used INT DEFAULT 0,
            api_calls INT DEFAULT 0,
            overage_tokens INT DEFAULT 0,
            overage_cost DECIMAL(10,2) DEFAULT 0.00,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES plans(id),
            UNIQUE KEY unique_user_date (user_id, date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    
    # 결제 로그 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            plan_id INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            payment_method VARCHAR(50) NOT NULL,
            payment_id VARCHAR(100) UNIQUE,
            status ENUM('pending', 'completed', 'failed', 'cancelled') DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    
    # 기본 플랜 데이터 삽입 (이미 존재하지 않는 경우)
    cursor.execute("""
        INSERT IGNORE INTO plans (id, name, price, request_limit, description, features, rate_limit_per_minute, is_active, is_popular, sort_order) VALUES
        (1, 'Demo', 0.00, 100, '데모 플랜', '{"analytics": "basic", "api_access": true, "ads": true}', 10, TRUE, FALSE, 0),
        (2, 'Free', 0.00, 1000, '무료 플랜', '{"analytics": "basic", "api_access": true, "ads": true}', 30, TRUE, FALSE, 1),
        (3, 'Starter', 29900.00, 50000, '스타터 플랜', '{"analytics": "standard", "api_access": true, "ads": false, "email_support": true}', 100, TRUE, TRUE, 2),
        (4, 'Pro', 79900.00, 200000, '프로 플랜', '{"analytics": "advanced", "api_access": true, "ads": false, "email_support": true, "custom_ui": true, "advanced_reports": true}', 500, TRUE, FALSE, 3)
    """)

def cleanup_password_reset_tokens() -> int:
    """만료되었거나 사용 완료 후 일정 기간 지난 토큰 정리. 삭제된 행 수 반환"""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM password_reset_tokens
                WHERE (used = TRUE AND created_at < NOW() - INTERVAL 1 DAY)
                   OR (expires_at < NOW() - INTERVAL 1 DAY)
                """
            )
            return cursor.rowcount if hasattr(cursor, 'rowcount') else 0


def cleanup_password_reset_codes() -> int:
    """만료되었거나 사용 완료 후 일정 기간 지난 6자리 코드 정리"""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM password_reset_codes
                WHERE (used = TRUE AND created_at < NOW() - INTERVAL 1 DAY)
                   OR (expires_at < NOW() - INTERVAL 1 DAY)
                """
            )
            return cursor.rowcount if hasattr(cursor, 'rowcount') else 0


def aggregate_request_statistics(days: int = 30) -> int:
    """최근 N일간 request_logs를 집계하여 request_statistics에 업서트한다.
    반환: 영향받은(업서트된) 행 수(참고용)
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO request_statistics (date, total_requests, success_count, failure_count)
                    SELECT DATE(request_time) AS date,
                           COUNT(*) AS total_requests,
                           SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) AS success_count,
                           SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS failure_count
                    FROM request_logs
                    WHERE request_time >= CURDATE() - INTERVAL {days} DAY
                    GROUP BY DATE(request_time)
                    ON DUPLICATE KEY UPDATE
                      total_requests=VALUES(total_requests),
                      success_count=VALUES(success_count),
                      failure_count=VALUES(failure_count)
                    """
                )
                return cursor.rowcount if hasattr(cursor, 'rowcount') else 0
    except Exception as e:
        print(f"집계 실패(request_statistics): {e}")
        return 0


def aggregate_error_stats_daily(days: int = 30) -> int:
    """최근 N일간 request_logs를 상태코드별로 집계하여 error_stats_daily에 업서트한다."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO error_stats_daily (date, status_code, count)
                    SELECT DATE(request_time) AS date, status_code, COUNT(*) AS cnt
                    FROM request_logs
                    WHERE request_time >= CURDATE() - INTERVAL {days} DAY
                    GROUP BY DATE(request_time), status_code
                    ON DUPLICATE KEY UPDATE count=VALUES(count)
                    """
                )
                return cursor.rowcount if hasattr(cursor, 'rowcount') else 0
    except Exception as e:
        print(f"집계 실패(error_stats_daily): {e}")
        return 0


def aggregate_endpoint_usage_daily(days: int = 30) -> int:
    """최근 N일간 request_logs를 엔드포인트(여기서는 api_key 기준)별로 집계하여
    endpoint_usage_daily에 업서트한다. 평균 응답시간은 request_logs.response_time(단위 ms 가정) 사용.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO endpoint_usage_daily (date, endpoint, requests, avg_ms)
                    SELECT DATE(request_time) AS date,
                           CONCAT('api_key:', COALESCE(api_key, '')) AS endpoint,
                           COUNT(*) AS requests,
                           ROUND(AVG(COALESCE(response_time, 0))) AS avg_ms
                    FROM request_logs
                    WHERE request_time >= CURDATE() - INTERVAL {days} DAY
                    GROUP BY DATE(request_time), COALESCE(api_key, '')
                    ON DUPLICATE KEY UPDATE
                      requests=VALUES(requests),
                      avg_ms=VALUES(avg_ms)
                    """
                )
                return cursor.rowcount if hasattr(cursor, 'rowcount') else 0
    except Exception as e:
        print(f"집계 실패(endpoint_usage_daily): {e}")
        return 0
