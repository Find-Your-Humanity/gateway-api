# RealCaptcha 데이터베이스 정리 가이드

## 📋 개요
RealCaptcha 프로젝트에서 사용하지 않는 테이블들을 정리하여 데이터베이스 구조를 최적화합니다.

## 🗑️ 제거 대상 테이블들

### 1. `user_sessions` 테이블
- **제거 이유**: JWT 기반 인증으로 대체됨
- **대체 테이블**: `refresh_tokens`
- **상태**: 사용 안함
- **영향**: 없음 (이미 사용하지 않음)

### 2. `popup_settings` 테이블
- **제거 이유**: 참조하는 `notices` 테이블이 존재하지 않음
- **상태**: 사용 안함
- **영향**: 없음 (이미 사용하지 않음)

### 3. `notices` 테이블
- **제거 이유**: 실제로 존재하지 않음 (참조만 됨)
- **상태**: 존재하지 않음
- **영향**: 없음

## ✅ 사용 중인 테이블들

### 핵심 사용자/인증 테이블
- `users` - 사용자 정보
- `api_keys` - API 키 관리
- `refresh_tokens` - JWT 리프레시 토큰
- `password_reset_tokens` - 비밀번호 재설정
- `password_reset_codes` - 비밀번호 재설정 코드
- `email_verification_codes` - 이메일 인증

### 요청 로그 테이블
- `request_logs` - API 요청 로그 (gateway-api)
- `api_request_logs` - API 요청 로그 (captcha-api)

### 캡차 관련 테이블
- `captcha_tokens` - 캡차 토큰 관리

### 통계/사용량 추적 테이블
- `daily_api_stats` - 일별 API 통계
- `daily_api_stats_by_key` - API 키별 일별 통계
- `daily_user_api_stats` - 사용자별 일별 통계
- `api_key_usage` - API 키 사용량
- `user_usage_summary` - 사용자 사용량 요약
- `user_usage_tracking` - 사용자 사용량 추적

### 요금제/결제 테이블
- `plans` - 요금제 정보
- `user_subscriptions` - 사용자 구독 정보
- `payment_logs` - 결제 로그

### 문의/고객지원 테이블
- `contact_requests` - 문의사항

### 시스템 통계 테이블
- `request_statistics` - 요청 통계
- `error_stats_daily` - 일별 에러 통계
- `endpoint_usage_daily` - 엔드포인트별 일별 사용량

## 🚀 실행 방법

### 1. 백업 생성 (권장)
```bash
mysqldump -h [HOST] -P [PORT] -u [USER] -p captcha > captcha_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 2. 정리 스크립트 실행
```bash
mysql -h [HOST] -P [PORT] -u [USER] -p < cleanup_unused_tables.sql
```

### 3. 결과 확인
```sql
USE captcha;
SHOW TABLES;
```

## ⚠️ 주의사항

1. **백업 필수**: 정리 작업 전 반드시 데이터베이스 백업을 생성하세요.
2. **테스트 환경**: 프로덕션 환경에서 실행하기 전에 테스트 환경에서 먼저 실행하세요.
3. **의존성 확인**: 다른 테이블에서 참조하는 외래키가 있는지 확인하세요.

## 📊 정리 후 예상 효과

- **데이터베이스 크기 감소**: 사용하지 않는 테이블 제거로 스토리지 절약
- **성능 향상**: 불필요한 테이블 스캔 제거
- **유지보수성 향상**: 명확한 테이블 구조로 관리 용이
- **보안 강화**: 사용하지 않는 테이블 제거로 공격 표면 감소

## 🔄 롤백 방법

정리 작업 후 문제가 발생한 경우:

```bash
# 백업 파일로 복원
mysql -h [HOST] -P [PORT] -u [USER] -p captcha < captcha_backup_YYYYMMDD_HHMMSS.sql
```

## 📝 변경 이력

- **2024-01-XX**: 초기 정리 스크립트 작성
- **2024-01-XX**: 사용하지 않는 테이블 식별 및 정리 계획 수립
