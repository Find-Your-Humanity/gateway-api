-- =====================================================
-- 요금제 관리 시스템 샘플 데이터
-- =====================================================

-- =====================================================
-- 1. 요금제 카탈로그 데이터
-- =====================================================
INSERT INTO plans (
    name, display_name, description, plan_type,
    price, billing_cycle,
    monthly_request_limit, concurrent_requests,
    features, rate_limit_per_minute,
    is_active, is_popular, sort_order
) VALUES
-- 무료 플랜
(
    'free', 'Free',
    '개인 개발자와 소규모 프로젝트를 위한 무료 플랜입니다.',
    'free',
    0.00, 'monthly',
    1000, 5,
    JSON_OBJECT(
        'captcha_basic', true,
        'email_support', false,
        'analytics', 'basic',
        'api_access', true,
        'custom_themes', false
    ),
    30,
    true, false, 1
),

-- 스타터 플랜
(
    'starter', 'Starter',
    '성장하는 비즈니스를 위한 기본 플랜입니다.',
    'paid',
    9900.00, 'monthly',
    10000, 10,
    JSON_OBJECT(
        'captcha_basic', true,
        'captcha_advanced', true,
        'email_support', true,
        'analytics', 'standard',
        'api_access', true,
        'custom_themes', true,
        'webhook_support', false
    ),
    100,
    true, true, 2
),

-- 프로 플랜
(
    'pro', 'Pro',
    '전문적인 서비스를 위한 고급 플랜입니다.',
    'paid',
    39000.00, 'monthly',
    100000, 25,
    JSON_OBJECT(
        'captcha_basic', true,
        'captcha_advanced', true,
        'captcha_invisible', true,
        'email_support', true,
        'phone_support', true,
        'analytics', 'advanced',
        'api_access', true,
        'custom_themes', true,
        'webhook_support', true,
        'white_labeling', true
    ),
    500,
    true, false, 3
),

-- 엔터프라이즈 플랜
(
    'enterprise', 'Enterprise',
    '대기업을 위한 맞춤형 엔터프라이즈 솔루션입니다.',
    'enterprise',
    199000.00, 'monthly',
    NULL, 100,
    JSON_OBJECT(
        'captcha_basic', true,
        'captcha_advanced', true,
        'captcha_invisible', true,
        'captcha_custom', true,
        'email_support', true,
        'phone_support', true,
        'dedicated_support', true,
        'analytics', 'enterprise',
        'api_access', true,
        'custom_themes', true,
        'webhook_support', true,
        'white_labeling', true,
        'sla_guarantee', true,
        'custom_integration', true
    ),
    2000,
    true, false, 4
);

-- =====================================================
-- 2. 기존 사용자들에게 구독 할당
-- =====================================================

-- admin 사용자에게 Enterprise 플랜 할당
INSERT INTO subscriptions (
    user_id, plan_id, started_at, expires_at, status, amount, payment_method, notes
) VALUES (
    5, -- admin (zeroorder31@gmail.com)
    4, -- Enterprise 플랜
    '2025-08-01 00:00:00',
    '2026-08-01 00:00:00',
    'active',
    199000.00,
    'manual',
    '관리자 계정 - 무료 Enterprise 플랜'
);

-- 일반 사용자들에게 다양한 플랜 할당
INSERT INTO subscriptions (
    user_id, plan_id, started_at, expires_at, status, amount, payment_method, notes
) VALUES 
-- user1에게 Free 플랜
(
    1, 1, -- user1, Free 플랜
    '2025-08-01 00:00:00', NULL, 'active',
    0.00, 'free', '무료 플랜 사용자'
),
-- user2에게 Starter 플랜
(
    2, 2, -- user2, Starter 플랜
    '2025-08-01 00:00:00', '2025-09-01 00:00:00', 'active',
    9900.00, 'card', '카드 결제'
),
-- jeonnamkyu에게 Pro 플랜
(
    4, 3, -- jeonnamkyu, Pro 플랜
    '2025-08-01 00:00:00', '2025-09-01 00:00:00', 'active',
    39000.00, 'bank', '계좌이체'
);

-- =====================================================
-- 3. 샘플 청구서 데이터
-- =====================================================
INSERT INTO invoices (
    subscription_id, user_id, invoice_number, invoice_date, due_date,
    subtotal, tax_amount, total_amount,
    billing_period_start, billing_period_end,
    description, status, paid_at
) VALUES
-- Starter 플랜 청구서
(
    2, 2, 'INV-2025-08-001', '2025-08-01', '2025-08-15',
    9000.00, 900.00, 9900.00,
    '2025-08-01', '2025-08-31',
    'Starter 플랜 - 8월 이용료',
    'paid', '2025-08-03 14:30:00'
),
-- Pro 플랜 청구서
(
    3, 4, 'INV-2025-08-002', '2025-08-01', '2025-08-15',
    35454.55, 3545.45, 39000.00,
    '2025-08-01', '2025-08-31',
    'Pro 플랜 - 8월 이용료',
    'paid', '2025-08-02 09:15:00'
);

-- =====================================================
-- 4. 샘플 결제 기록
-- =====================================================
INSERT INTO payments (
    invoice_id, subscription_id, user_id,
    payment_id, amount, payment_method, payment_gateway,
    status, processed_at
) VALUES
-- Starter 플랜 결제
(
    1, 2, 2,
    'PAY_20250803_001', 9900.00, 'card', 'toss',
    'completed', '2025-08-03 14:30:15'
),
-- Pro 플랜 결제
(
    2, 3, 4,
    'PAY_20250802_002', 39000.00, 'bank', 'kakao',
    'completed', '2025-08-02 09:15:30'
);

-- =====================================================
-- 5. 샘플 사용량 로그 (최근 며칠)
-- =====================================================
INSERT INTO usage_logs (
    user_id, subscription_id, api_endpoint, request_method,
    tokens_consumed, response_time_ms, status_code,
    user_ip, logged_at
) VALUES
-- Free 플랜 사용자 (user1)
(1, 1, '/api/captcha/generate', 'POST', 1, 120, 200, '192.168.1.10', '2025-08-18 10:30:00'),
(1, 1, '/api/captcha/verify', 'POST', 1, 85, 200, '192.168.1.10', '2025-08-18 10:35:00'),
(1, 1, '/api/captcha/generate', 'POST', 1, 95, 200, '192.168.1.10', '2025-08-18 14:20:00'),

-- Starter 플랜 사용자 (user2)
(2, 2, '/api/captcha/generate', 'POST', 1, 100, 200, '203.156.78.45', '2025-08-18 09:15:00'),
(2, 2, '/api/captcha/verify', 'POST', 1, 75, 200, '203.156.78.45', '2025-08-18 09:20:00'),
(2, 2, '/api/captcha/advanced', 'POST', 2, 150, 200, '203.156.78.45', '2025-08-18 11:40:00'),

-- Pro 플랜 사용자 (jeonnamkyu)
(4, 3, '/api/captcha/invisible', 'POST', 3, 200, 200, '210.100.50.123', '2025-08-18 08:30:00'),
(4, 3, '/api/captcha/verify', 'POST', 1, 60, 200, '210.100.50.123', '2025-08-18 08:35:00'),
(4, 3, '/api/analytics/reports', 'GET', 1, 300, 200, '210.100.50.123', '2025-08-18 16:00:00');

-- =====================================================
-- 6. 월별 사용량 집계 샘플
-- =====================================================
INSERT INTO usage_summaries (
    user_id, subscription_id, year, month,
    total_requests, total_tokens, success_requests, failed_requests,
    avg_response_time_ms, last_updated
) VALUES
-- 8월 집계 (부분)
(1, 1, 2025, 8, 45, 45, 43, 2, 102.5, NOW()),
(2, 2, 2025, 8, 128, 145, 125, 3, 95.8, NOW()),
(4, 3, 2025, 8, 342, 456, 340, 2, 180.2, NOW()),

-- 7월 집계 (전체월)
(2, 2, 2025, 7, 1250, 1380, 1245, 5, 87.3, '2025-08-01 00:00:00'),
(4, 3, 2025, 7, 8960, 12450, 8955, 5, 165.7, '2025-08-01 00:00:00');
