# Account Management and Metrics APIs

## Enterprise Account Management/Metrics Guide

Learn how to use account management and metrics APIs for enterprise accounts.

### Account Management API

```javascript
// Get account information
const accountInfo = await fetch('/api/enterprise/account', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
});

// Get usage statistics
const usageStats = await fetch('/api/enterprise/usage', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
});
```

### Metrics API

- **Request Count**: Daily/monthly captcha request count
- **Success Rate**: Captcha success/failure ratio
- **Response Time**: Average response time
- **Regional Statistics**: Usage statistics by country/region

### Dashboard Features

- Real-time monitoring
- Usage analytics
- Performance metrics
- Alert settings 