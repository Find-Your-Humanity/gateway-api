# Invisible Captcha

## Invisible Captcha Implementation Guide

Learn how to implement invisible captcha that automatically verifies users without requiring them to solve captcha manually.

### Basic Configuration

```javascript
REAL.init({
  siteKey: 'YOUR_API_KEY',
  container: '#captcha-container',
  size: 'invisible',
  callback: function(token) {
    // Token generated automatically
    console.log('Invisible captcha token:', token);
  }
});
```

### Use Cases

1. **Form Submission**: Automatically verify captcha when user submits a form
2. **Button Click**: Automatically verify captcha when specific button is clicked
3. **Page Load**: Automatically verify captcha when page loads

### Benefits

- Enhanced user experience
- Automated bot blocking
- No explicit user interaction required 