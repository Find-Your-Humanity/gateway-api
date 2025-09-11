-- 사용하지 않는 테이블들 정리 스크립트
-- RealCaptcha 프로젝트에서 실제로 사용하지 않는 테이블들을 제거

USE captcha;

-- 1. user_sessions 테이블 제거 (JWT 기반 인증으로 대체됨)
-- 이 테이블은 현재 사용되지 않으며, refresh_tokens 테이블로 대체됨
DROP TABLE IF EXISTS `user_sessions`;

-- 2. popup_settings 테이블 제거 (참조하는 notices 테이블이 존재하지 않음)
-- 이 테이블은 notices 테이블을 참조하지만 notices 테이블이 존재하지 않음
DROP TABLE IF EXISTS `popup_settings`;

-- 3. notices 테이블이 존재한다면 제거 (현재 사용되지 않음)
-- 실제로는 존재하지 않지만 혹시 모르니 확인 후 제거
DROP TABLE IF EXISTS `notices`;

-- 정리 완료 후 테이블 목록 확인
SHOW TABLES;

-- 사용 중인 주요 테이블들 확인
SELECT 
    TABLE_NAME,
    TABLE_ROWS,
    CREATE_TIME,
    UPDATE_TIME
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'captcha' 
    AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
