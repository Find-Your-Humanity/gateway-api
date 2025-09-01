# Mobile App SDKs

Integrate REAL captcha into your iOS and Android applications for comprehensive bot protection.

## Overview

REAL provides native SDKs for mobile platforms, ensuring seamless integration with your mobile apps while maintaining the same security standards as web implementations.

## iOS SDK

### Installation

#### CocoaPods
```ruby
pod 'RealCaptcha', '~> 1.0.0'
```

#### Swift Package Manager
```swift
dependencies: [
    .package(url: "https://github.com/realcatcha/ios-sdk.git", from: "1.0.0")
]
```

### Basic Usage

```swift
import RealCaptcha

class ViewController: UIViewController {
    private var captchaView: RealCaptchaView!
    
    override func viewDidLoad() {
        super.viewDidLoad()
        setupCaptcha()
    }
    
    private func setupCaptcha() {
        captchaView = RealCaptchaView()
        captchaView.delegate = self
        captchaView.siteKey = "YOUR_API_KEY_HERE"
        
        // Add to view hierarchy
        view.addSubview(captchaView)
        
        // Setup constraints
        captchaView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            captchaView.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            captchaView.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            captchaView.widthAnchor.constraint(equalToConstant: 300),
            captchaView.heightAnchor.constraint(equalToConstant: 80)
        ])
    }
}

// MARK: - RealCaptchaDelegate
extension ViewController: RealCaptchaDelegate {
    func captchaDidSucceed(_ captcha: RealCaptchaView, token: String) {
        print("Captcha succeeded with token: \(token)")
        // Handle success - submit form, etc.
    }
    
    func captchaDidFail(_ captcha: RealCaptchaView, error: Error) {
        print("Captcha failed with error: \(error)")
        // Handle failure
    }
    
    func captchaDidExpire(_ captcha: RealCaptchaView) {
        print("Captcha expired")
        // Handle expiration
    }
}
```

### Advanced Configuration

```swift
// Custom theme
captchaView.theme = .dark

// Custom size
captchaView.size = .compact

// Custom language
captchaView.language = "ko"

// Custom appearance
captchaView.cornerRadius = 8.0
captchaView.borderWidth = 1.0
captchaView.borderColor = UIColor.systemBlue
```

## Android SDK

### Installation

#### Gradle
```gradle
dependencies {
    implementation 'com.realcatcha:android-sdk:1.0.0'
}
```

### Basic Usage

```kotlin
import com.realcatcha.RealCaptchaView
import com.realcatcha.RealCaptchaListener

class MainActivity : AppCompatActivity() {
    private lateinit var captchaView: RealCaptchaView
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        setupCaptcha()
    }
    
    private fun setupCaptcha() {
        captchaView = findViewById(R.id.captcha_view)
        
        captchaView.setSiteKey("YOUR_API_KEY_HERE")
        captchaView.setListener(object : RealCaptchaListener {
            override fun onSuccess(token: String) {
                Log.d("Captcha", "Success: $token")
                // Handle success
            }
            
            override fun onFailure(error: String) {
                Log.e("Captcha", "Failure: $error")
                // Handle failure
            }
            
            override fun onExpired() {
                Log.d("Captcha", "Expired")
                // Handle expiration
            }
        })
    }
}
```

### Layout XML

```xml
<com.realcatcha.RealCaptchaView
    android:id="@+id/captcha_view"
    android:layout_width="300dp"
    android:layout_height="80dp"
    android:layout_gravity="center"
    app:siteKey="YOUR_API_KEY_HERE" />
```

### Advanced Configuration

```kotlin
// Custom theme
captchaView.setTheme(RealCaptchaTheme.DARK)

// Custom size
captchaView.setSize(RealCaptchaSize.COMPACT)

// Custom language
captchaView.setLanguage("ko")

// Custom appearance
captchaView.setCornerRadius(8f)
captchaView.setBorderWidth(1f)
captchaView.setBorderColor(Color.BLUE)
```

## React Native

### Installation

```bash
npm install @realcatcha/react-native
# or
yarn add @realcaptcha/react-native
```

### Usage

```jsx
import React from 'react';
import { RealCaptcha } from '@realcatcha/react-native';

const App = () => {
  const handleSuccess = (token) => {
    console.log('Captcha success:', token);
  };

  const handleFailure = (error) => {
    console.log('Captcha failure:', error);
  };

  const handleExpired = () => {
    console.log('Captcha expired');
  };

  return (
    <RealCaptcha
      siteKey="YOUR_API_KEY_HERE"
      onSuccess={handleSuccess}
      onFailure={handleFailure}
      onExpired={handleExpired}
      style={{ width: 300, height: 80 }}
    />
  );
};
```

## Flutter

### Installation

```yaml
dependencies:
  realcaptcha: ^1.0.0
```

### Usage

```dart
import 'package:realcaptcha/realcaptcha.dart';

class MyWidget extends StatefulWidget {
  @override
  _MyWidgetState createState() => _MyWidgetState();
}

class _MyWidgetState extends State<MyWidget> {
  @override
  Widget build(BuildContext context) {
    return RealCaptcha(
      siteKey: 'YOUR_API_KEY_HERE',
      onSuccess: (token) {
        print('Captcha success: $token');
      },
      onFailure: (error) {
        print('Captcha failure: $error');
      },
      onExpired: () {
        print('Captcha expired');
      },
    );
  }
}
```

## Common Features

All mobile SDKs support:

- **Custom Themes**: Light, dark, and custom themes
- **Multiple Sizes**: Compact, normal, and large sizes
- **Language Support**: Multiple language options
- **Accessibility**: VoiceOver and TalkBack support
- **Offline Support**: Basic offline functionality
- **Analytics**: Usage statistics and performance metrics

## Best Practices

1. **Placement**: Position captcha above submit buttons
2. **Size**: Use appropriate size for your UI
3. **Theme**: Match your app's design language
4. **Error Handling**: Provide clear feedback on failures
5. **Testing**: Test on various devices and screen sizes

## Troubleshooting

### Common Issues

1. **Widget Not Displaying**: Check API key and network connectivity
2. **Token Validation Fails**: Verify secret key and server configuration
3. **Performance Issues**: Ensure proper memory management
4. **Accessibility Problems**: Test with screen readers

### Support

For technical support:
- Check our documentation
- Review sample projects
- Contact our support team
- Join our developer community

Mobile SDKs provide the same robust protection as web implementations while maintaining native app performance and user experience. 