# API Key Usage Guide

Learn how to integrate REAL captcha into your website using your issued API key and Secret key step by step.

## API Key Overview

The API key is used to render the widget on the frontend, and the Secret key is used to verify tokens on the server side. Both keys must be kept secure.

## Frontend Integration

1. Add REAL script to HTML
2. Create widget container
3. Initialize widget with API key
4. Set callback functions

Example code:

```html
<!DOCTYPE html>
<html>
<head>
    <title>REAL Captcha Example</title>
    <script src="https://1df60f5faf3b4f2f992ced2edbae22ad.kakaoiedge.com/latest/realcaptcha-widget.min.js"></script>
</head>
<body>
    <form id="login-form">
        <input type="email" placeholder="Email" required>
        <input type="password" placeholder="Password" required>
        
        <!-- REAL Widget Container -->
        <div id="real-captcha"></div>
        
        <button type="submit">Login</button>
    </form>

    <script>
        // Initialize widget with API key
        REAL.init({
            siteKey: 'YOUR_API_KEY_HERE',
            container: '#real-captcha',
            callback: function(token) {
                // Execute when captcha succeeds
                console.log('Captcha success:', token);
                document.getElementById('login-form').submit();
            },
            'expired-callback': function() {
                // Execute when token expires
                console.log('Token expired');
                REAL.reset();
            }
        });
    </script>
</body>
</html>
```

## Backend Verification

How to verify tokens received from the frontend on the server.

Node.js example:
```javascript
const axios = require('axios');

async function verifyCaptcha(token) {
    try {
        const response = await axios.post('https://gateway.realcatcha.com/api/captcha/verify', {
            secret: 'YOUR_SECRET_KEY_HERE',
            response: token
        });
        
        if (response.data.success) {
            console.log('Captcha verification successful');
            return true;
        } else {
            console.log('Captcha verification failed:', response.data.error);
            return false;
        }
    } catch (error) {
        console.error('Verification error:', error);
        return false;
    }
}

// Express.js route example
app.post('/login', async (req, res) => {
    const { email, password, captchaToken } = req.body;
    
    // Verify captcha
    const isValidCaptcha = await verifyCaptcha(captchaToken);
    
    if (!isValidCaptcha) {
        return res.status(400).json({ error: 'Captcha verification failed' });
    }
    
    // Proceed with login logic
    // ...
});
``` 