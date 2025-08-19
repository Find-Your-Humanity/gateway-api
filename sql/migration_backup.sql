-- =====================================================
-- 기존 데이터 백업 및 마이그레이션 스크립트
-- =====================================================

-- ⚠️ 주의: 이 스크립트를 실행하기 전에 전체 DB 백업을 권장합니다!
-- mysqldump -u username -p captcha > captcha_backup_$(date +%Y%m%d_%H%M%S).sql

-- =====================================================
-- 1단계: 기존 테이블 백업
-- =====================================================

-- 기존 plans 테이블 백업
CREATE TABLE plans_backup_20250819 AS 
SELECT * FROM plans;

-- 기존 user_subscriptions 테이블 백업 (있다면)
CREATE TABLE user_subscriptions_backup_20250819 AS 
SELECT * FROM user_subscriptions;

-- =====================================================
-- 2단계: 기존 테이블 삭제 (순서 중요 - FK 관계 고려)
-- =====================================================

-- 외래키 제약 확인
SELECT 
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'captcha'
AND REFERENCED_TABLE_NAME IN ('plans', 'user_subscriptions');

-- 의존 테이블들 삭제 (FK 관계가 있다면)
DROP TABLE IF EXISTS user_subscriptions;

-- 기존 plans 테이블 삭제
DROP TABLE IF EXISTS plans;

-- =====================================================
-- 3단계: 새로운 스키마 적용
-- =====================================================
-- 이 부분에서 pricing_schema.sql 파일을 실행하세요
-- SOURCE /path/to/pricing_schema.sql;

-- =====================================================
-- 4단계: 기존 데이터 마이그레이션 (필요시)
-- =====================================================

-- 기존 plans 데이터가 있었다면 새 형식으로 변환
-- 예시 (실제 기존 테이블 구조에 맞게 수정 필요):
/*
INSERT INTO plans (
    name, display_name, description, plan_type,
    price, monthly_request_limit, concurrent_requests,
    is_active, sort_order
)
SELECT 
    LOWER(name) as name,
    name as display_name,
    description,
    CASE 
        WHEN price = 0 THEN 'free'
        WHEN price < 50000 THEN 'paid'
        ELSE 'enterprise'
    END as plan_type,
    price,
    request_limit as monthly_request_limit,
    10 as concurrent_requests, -- 기본값
    TRUE as is_active,
    id as sort_order
FROM plans_backup_20250819;
*/

-- 기존 user_subscriptions 데이터가 있었다면 새 형식으로 변환
-- 예시:
/*
INSERT INTO subscriptions (
    user_id, plan_id, started_at, expires_at,
    status, amount, payment_method
)
SELECT 
    user_id,
    plan_id,
    start_date as started_at,
    end_date as expires_at,
    'active' as status,
    (SELECT price FROM plans p WHERE p.id = ubs.plan_id) as amount,
    'manual' as payment_method
FROM user_subscriptions_backup_20250819 ubs
WHERE end_date IS NULL OR end_date > NOW();
*/

-- =====================================================
-- 5단계: 데이터 검증
-- =====================================================

-- 새로운 테이블들이 제대로 생성되었는지 확인
SHOW TABLES LIKE '%plans%';
SHOW TABLES LIKE '%subscription%';
SHOW TABLES LIKE '%invoice%';
SHOW TABLES LIKE '%payment%';
SHOW TABLES LIKE '%usage%';

-- 테이블 구조 확인
DESCRIBE plans;
DESCRIBE subscriptions;
DESCRIBE invoices;
DESCRIBE payments;
DESCRIBE usage_logs;
DESCRIBE usage_summaries;

-- 외래키 제약 확인
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'captcha'
AND TABLE_NAME IN ('subscriptions', 'invoices', 'payments', 'usage_logs', 'usage_summaries');

-- 데이터 개수 확인
SELECT 'plans' as table_name, COUNT(*) as count FROM plans
UNION ALL
SELECT 'subscriptions' as table_name, COUNT(*) as count FROM subscriptions
UNION ALL
SELECT 'invoices' as table_name, COUNT(*) as count FROM invoices
UNION ALL
SELECT 'payments' as table_name, COUNT(*) as count FROM payments
UNION ALL
SELECT 'usage_logs' as table_name, COUNT(*) as count FROM usage_logs
UNION ALL
SELECT 'usage_summaries' as table_name, COUNT(*) as count FROM usage_summaries;
