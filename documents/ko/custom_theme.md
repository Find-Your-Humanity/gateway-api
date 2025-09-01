# 사용자 정의 테마

## 위젯 테마 커스터마이징 가이드

REAL 캡차 위젯의 테마를 웹사이트에 맞게 커스터마이징하는 방법을 알아보세요.

### 기본 테마 옵션

```javascript
REAL.init({
  siteKey: 'YOUR_API_KEY',
  container: '#captcha-container',
  theme: 'light', // light, dark
  // 또는
  theme: 'dark'
});
```

### CSS 커스터마이징

```css
/* 위젯 컨테이너 스타일링 */
#captcha-container {
  border: 2px solid #007bff;
  border-radius: 8px;
  padding: 10px;
  background-color: #f8f9fa;
}

/* 위젯 내부 요소 스타일링 */
.real-captcha-widget {
  font-family: 'Arial', sans-serif;
  color: #333;
}
```

### 고급 커스터마이징

- **색상 변경**: 브랜드 색상에 맞춰 조정
- **폰트 변경**: 웹사이트 폰트와 일치
- **크기 조정**: 레이아웃에 맞춰 크기 조정
- **애니메이션**: 부드러운 전환 효과 추가 