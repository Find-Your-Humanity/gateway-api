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
