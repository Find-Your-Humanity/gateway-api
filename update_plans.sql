-- =====================================================
-- 요금제 정보 업데이트 스크립트
-- 작성일: 2024-12-19
-- 목적: Basic, Plus, Pro 플랜 정보 업데이트
-- =====================================================

-- 기존 데이터 백업 (선택사항)
-- CREATE TABLE plans_backup_20241219 AS SELECT * FROM plans;

-- =====================================================
-- 1. 기존 plans 테이블 데이터 삭제 (필요시)
-- =====================================================
-- DELETE FROM plans;

-- =====================================================
-- 2. 새로운 요금제 데이터 삽입
-- =====================================================

-- Basic 플랜 (무료)
INSERT INTO plans (
    name, 
    display_name, 
    description, 
    plan_type, 
    price, 
    currency, 
    billing_cycle,
    monthly_request_limit, 
    concurrent_requests,
    rate_limit_per_minute,
    is_active, 
    is_popular, 
    sort_order,
    features
) VALUES (
    'basic',
    'Basic',
    '무료 플랜 - 기본적인 캡차 서비스 이용 가능',
    'free',
    0.00,
    'KRW',
    'monthly',
    50000,
    5,
    10,
    TRUE,
    FALSE,
    1,
    JSON_OBJECT(
        'captcha_types', JSON_ARRAY('image', 'handwriting'),
        'api_access', true,
        'support', 'community',
        'analytics', false
    )
) ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    description = VALUES(description),
    plan_type = VALUES(plan_type),
    price = VALUES(price),
    monthly_request_limit = VALUES(monthly_request_limit),
    concurrent_requests = VALUES(concurrent_requests),
    rate_limit_per_minute = VALUES(rate_limit_per_minute),
    is_active = VALUES(is_active),
    is_popular = VALUES(is_popular),
    sort_order = VALUES(sort_order),
    features = VALUES(features),
    updated_at = CURRENT_TIMESTAMP;

-- Plus 플랜 (유료)
INSERT INTO plans (
    name, 
    display_name, 
    description, 
    plan_type, 
    price, 
    currency, 
    billing_cycle,
    monthly_request_limit, 
    concurrent_requests,
    rate_limit_per_minute,
    is_active, 
    is_popular, 
    sort_order,
    features
) VALUES (
    'plus',
    'Plus',
    'Plus 플랜 - 중소기업에 적합한 캡차 서비스',
    'paid',
    25000.00,
    'KRW',
    'monthly',
    250000,
    20,
    50,
    TRUE,
    TRUE,
    2,
    JSON_OBJECT(
        'captcha_types', JSON_ARRAY('image', 'handwriting', 'abstract'),
        'api_access', true,
        'support', 'email',
        'analytics', true,
        'custom_theme', true,
        'priority_support', false
    )
) ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    description = VALUES(description),
    plan_type = VALUES(plan_type),
    price = VALUES(price),
    monthly_request_limit = VALUES(monthly_request_limit),
    concurrent_requests = VALUES(concurrent_requests),
    rate_limit_per_minute = VALUES(rate_limit_per_minute),
    is_active = VALUES(is_active),
    is_popular = VALUES(is_popular),
    sort_order = VALUES(sort_order),
    features = VALUES(features),
    updated_at = CURRENT_TIMESTAMP;

-- Pro 플랜 (고급)
INSERT INTO plans (
    name, 
    display_name, 
    description, 
    plan_type, 
    price, 
    currency, 
    billing_cycle,
    monthly_request_limit, 
    concurrent_requests,
    rate_limit_per_minute,
    is_active, 
    is_popular, 
    sort_order,
    features
) VALUES (
    'pro',
    'Pro',
    'Pro 플랜 - 대기업 및 고용량 사용자용 프리미엄 서비스',
    'paid',
    100000.00,
    'KRW',
    'monthly',
    1000000,
    100,
    200,
    TRUE,
    FALSE,
    3,
    JSON_OBJECT(
        'captcha_types', JSON_ARRAY('image', 'handwriting', 'abstract', 'behavioral'),
        'api_access', true,
        'support', 'priority',
        'analytics', true,
        'custom_theme', true,
        'priority_support', true,
        'sla', '99.9%',
        'custom_integration', true
    )
) ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    description = VALUES(description),
    plan_type = VALUES(plan_type),
    price = VALUES(price),
    monthly_request_limit = VALUES(monthly_request_limit),
    concurrent_requests = VALUES(concurrent_requests),
    rate_limit_per_minute = VALUES(rate_limit_per_minute),
    is_active = VALUES(is_active),
    is_popular = VALUES(is_popular),
    sort_order = VALUES(sort_order),
    features = VALUES(features),
    updated_at = CURRENT_TIMESTAMP;

-- =====================================================
-- 3. 업데이트 결과 확인
-- =====================================================
SELECT 
    id,
    name,
    display_name,
    plan_type,
    price,
    monthly_request_limit,
    rate_limit_per_minute,
    is_active,
    is_popular,
    sort_order,
    created_at,
    updated_at
FROM plans 
ORDER BY sort_order;

-- =====================================================
-- 4. 요약 정보 출력
-- =====================================================
SELECT 
    COUNT(*) as total_plans,
    SUM(CASE WHEN plan_type = 'free' THEN 1 ELSE 0 END) as free_plans,
    SUM(CASE WHEN plan_type = 'paid' THEN 1 ELSE 0 END) as paid_plans,
    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_plans
FROM plans;

