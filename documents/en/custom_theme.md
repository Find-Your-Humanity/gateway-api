# Custom Themes

## Widget Theme Customization Guide

Learn how to customize REAL captcha widget theme to match your website design.

### Basic Theme Options

```javascript
REAL.init({
  siteKey: 'YOUR_API_KEY',
  container: '#captcha-container',
  theme: 'light', // light, dark
  // or
  theme: 'dark'
});
```

### CSS Customization

```css
/* Widget container styling */
#captcha-container {
  border: 2px solid #007bff;
  border-radius: 8px;
  padding: 10px;
  background-color: #f8f9fa;
}

/* Widget internal element styling */
.real-captcha-widget {
  font-family: 'Arial', sans-serif;
  color: #333;
}
```

### Advanced Customization

- **Color Changes**: Adjust to match brand colors
- **Font Changes**: Match website fonts
- **Size Adjustments**: Adjust size to fit layout
- **Animations**: Add smooth transition effects 