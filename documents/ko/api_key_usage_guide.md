# API 키 사용 가이드

발급받은 API 키와 Secret 키를 사용하여 REAL 캡차를 웹사이트에 통합하는 방법을 단계별로 알아보세요.

## API 키 개요

API 키는 프론트엔드에서 위젯을 렌더링하는 데 사용되고, Secret 키는 서버 사이드에서 토큰을 검증하는 데 사용됩니다. 두 키 모두 안전하게 보관해야 합니다.

## 프론트엔드 통합

1. HTML에 REAL 스크립트 추가
2. 위젯 컨테이너 생성
3. API 키로 위젯 초기화
4. 콜백 함수 설정

예시 코드:

```html
<!DOCTYPE html>
<html>
<head>
    <title>REAL Captcha 예제</title>
    <script src="https://1df60f5faf3b4f2f992ced2edbae22ad.kakaoiedge.com/latest/realcaptcha-widget.min.js"></script>
</head>
<body>
    <form id="login-form">
        <input type="email" placeholder="이메일" required>
        <input type="password" placeholder="비밀번호" required>
        
        <!-- REAL 위젯 컨테이너 -->
        <div id="real-captcha"></div>
        
        <button type="submit">로그인</button>
    </form>

    <script>
        // API 키로 위젯 초기화
        REAL.init({
            siteKey: 'YOUR_API_KEY_HERE',
            container: '#real-captcha',
            callback: function(token) {
                // 캡차 성공 시 실행
                console.log('캡차 성공:', token);
                document.getElementById('login-form').submit();
            },
            'expired-callback': function() {
                // 토큰 만료 시 실행
                console.log('토큰 만료');
                REAL.reset();
            }
        });
    </script>
</body>
</html>
```

## 백엔드 검증

프론트엔드에서 받은 토큰을 서버에서 검증하는 방법입니다.

Node.js 예시:
```javascript
const axios = require('axios');

async function verifyCaptcha(token) {
    try {
        const response = await axios.post('https://gateway.realcatcha.com/api/captcha/verify', {
            secret: 'YOUR_SECRET_KEY_HERE',
            response: token
        });
        
        if (response.data.success) {
            console.log('캡차 검증 성공');
            return true;
        } else {
            console.log('캡차 검증 실패:', response.data.error);
            return false;
        }
    } catch (error) {
        console.error('검증 오류:', error);
        return false;
    }
}

// Express.js 라우트 예시
app.post('/login', async (req, res) => {
    const { email, password, captchaToken } = req.body;
    
    // 캡차 검증
    const isValidCaptcha = await verifyCaptcha(captchaToken);
    
    if (!isValidCaptcha) {
        return res.status(400).json({ error: '캡차 검증 실패' });
    }
    
    // 로그인 로직 진행
    // ...
});
``` 