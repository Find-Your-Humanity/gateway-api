# Switching from reCAPTCHA to REAL

If you're currently using Google reCAPTCHA, you can easily transition to REAL captcha.

## Why Switch?

- **Performance Improvement**: Faster loading and response times
- **Better User Experience**: Less intrusive interface
- **API Compatibility**: Similar structure to existing reCAPTCHA code
- **Enhanced Security**: Latest security technologies

## Migration Steps

### 1. Get API Keys
- Issue new API key and Secret key from REAL dashboard
- Backup and remove existing reCAPTCHA keys

### 2. Change Script
```html
<!-- Old reCAPTCHA -->
<script src="https://www.google.com/recaptcha/api.js"></script>

<!-- New REAL -->
<script src="https://1df60f5faf3b4f2f992ced2edbae22ad.kakaoiedge.com/latest/realcaptcha-widget.min.js"></script>
```

### 3. Change Widget Initialization
```javascript
// Old reCAPTCHA
grecaptcha.render('captcha-container', {
  'sitekey': 'your-recaptcha-site-key'
});

// New REAL
REAL.init({
  siteKey: 'your-real-api-key',
  container: '#captcha-container'
});
```

### 4. Change Callback Functions
```javascript
// Old reCAPTCHA
function onCaptchaSuccess(token) {
  // Handle token
}

// New REAL
REAL.init({
  siteKey: 'your-real-api-key',
  container: '#captcha-container',
  callback: function(token) {
    // Handle token
  }
});
```

### 5. Change Server Verification
```javascript
// Old reCAPTCHA
const verification = await fetch('https://www.google.com/recaptcha/api/siteverify', {
  method: 'POST',
  body: new URLSearchParams({
    secret: 'your-recaptcha-secret',
    response: token
  })
});

// New REAL
const verification = await fetch('https://gateway.realcatcha.com/api/captcha/verify', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    secret: 'your-real-secret-key',
    response: token
  })
});
```

## Maintaining Compatibility

REAL is designed to be compatible with reCAPTCHA's main APIs:

- `render()` method support
- `onload` callback support
- `theme`, `size`, `tabindex` attribute support
- Same response token structure

## Testing and Validation

After migration, verify the following:

1. **Widget Display**: Captcha widget renders correctly
2. **User Interaction**: Users can complete the captcha
3. **Token Generation**: Valid tokens are generated on success
4. **Server Verification**: Token verification works on server
5. **Error Handling**: Appropriate error messages on failure

## Troubleshooting

If issues occur during migration:

1. **Check Browser Console**: Look for JavaScript error messages
2. **Check Network Tab**: Verify API call status
3. **Validate Token**: Ensure generated tokens are in correct format
4. **Check Domain Settings**: Verify current domain is registered with API key

## After Complete Migration

Once all functionality is confirmed working:

1. Remove old reCAPTCHA related code
2. Remove unnecessary dependencies
3. Monitor performance and optimize
4. Collect user feedback and improve

Transitioning to REAL provides better user experience and security. 