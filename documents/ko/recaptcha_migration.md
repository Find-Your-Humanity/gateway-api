# reCAPTCHA에서 REAL로 전환하기

기존 Google reCAPTCHA를 사용하고 있다면, REAL 캡차로 쉽게 전환할 수 있습니다.

## 전환 이유

- **성능 향상**: 더 빠른 로딩과 응답 시간
- **사용자 경험 개선**: 덜 방해적인 인터페이스
- **API 호환성**: 기존 reCAPTCHA 코드와 유사한 구조
- **보안 강화**: 최신 보안 기술 적용

## 전환 단계

### 1. API 키 발급
- REAL 대시보드에서 새로운 API 키와 Secret 키 발급
- 기존 reCAPTCHA 키는 백업 후 제거

### 2. 스크립트 변경
```html
<!-- 기존 reCAPTCHA -->
<script src="https://www.google.com/recaptcha/api.js"></script>

<!-- 새로운 REAL -->
<script src="https://1df60f5faf3b4f2f992ced2edbae22ad.kakaoiedge.com/latest/realcaptcha-widget.min.js"></script>
```

### 3. 위젯 초기화 변경
```javascript
// 기존 reCAPTCHA
grecaptcha.render('captcha-container', {
  'sitekey': 'your-recaptcha-site-key'
});

// 새로운 REAL
REAL.init({
  siteKey: 'your-real-api-key',
  container: '#captcha-container'
});
```

### 4. 콜백 함수 변경
```javascript
// 기존 reCAPTCHA
function onCaptchaSuccess(token) {
  // 토큰 처리
}

// 새로운 REAL
REAL.init({
  siteKey: 'your-real-api-key',
  container: '#captcha-container',
  callback: function(token) {
    // 토큰 처리
  }
});
```

### 5. 서버 검증 변경
```javascript
// 기존 reCAPTCHA
const verification = await fetch('https://www.google.com/recaptcha/api/siteverify', {
  method: 'POST',
  body: new URLSearchParams({
    secret: 'your-recaptcha-secret',
    response: token
  })
});

// 새로운 REAL
const verification = await fetch('https://gateway.realcatcha.com/api/captcha/verify', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    secret: 'your-real-secret-key',
    response: token
  })
});
```

## 호환성 유지

REAL은 reCAPTCHA의 주요 API와 호환되도록 설계되었습니다:

- `render()` 메서드 지원
- `onload` 콜백 지원
- `theme`, `size`, `tabindex` 속성 지원
- 동일한 응답 토큰 구조

## 테스트 및 검증

전환 후 다음 사항들을 확인하세요:

1. **위젯 표시**: 캡차 위젯이 정상적으로 렌더링되는지
2. **사용자 상호작용**: 사용자가 캡차를 완료할 수 있는지
3. **토큰 생성**: 성공 시 유효한 토큰이 생성되는지
4. **서버 검증**: 서버에서 토큰 검증이 정상 작동하는지
5. **에러 처리**: 실패 시 적절한 에러 메시지가 표시되는지

## 문제 해결

전환 중 문제가 발생하면:

1. **브라우저 콘솔 확인**: JavaScript 오류 메시지 확인
2. **네트워크 탭 확인**: API 호출 상태 확인
3. **토큰 유효성 검증**: 생성된 토큰이 올바른 형식인지 확인
4. **도메인 설정 확인**: API 키에 현재 도메인이 등록되어 있는지 확인

## 완전 전환 후

모든 기능이 정상 작동하는 것을 확인한 후:

1. 기존 reCAPTCHA 관련 코드 제거
2. 불필요한 의존성 제거
3. 성능 모니터링 및 최적화
4. 사용자 피드백 수집 및 개선

REAL로의 전환을 통해 더 나은 사용자 경험과 보안을 제공할 수 있습니다. 