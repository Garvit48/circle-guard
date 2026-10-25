# Local verification

Environment: Apple Silicon macOS, Xcode 27.1, iPhone 18 Pro / iOS 27 simulator, Android API 35 ARM64 emulator. Added development tools and packages are installed inside this project.

| Check | Result |
| --- | --- |
| Shared Kotlin JVM tests | 5 passed |
| Python real-HTTP integration tests | 8 passed |
| Kotlin/Native iOS simulator framework | Built |
| Native SwiftUI iOS app | Built and launched |
| iOS XCUITest: create group + receive another member’s simulated exit | Passed |
| Android debug APK | Built and installed |
| Android lint | Passed |
| Android instrumentation: fake-location buttons, recipient-only single alert, reverse alert, OS notification | Passed |
| Optional APNs Python dependencies | Installed in `.venv`; imports verified |

Real Apple push delivery, physical-device background behavior, distribution signing, and store submission have not been tested. Apple push credentials are not supplied. Without APNs, local iOS notifications are delivered while the receiving app runs, and missed events appear on resume.

Useful artifacts:
- `androidApp/build/outputs/apk/debug/androidApp-debug.apk`
- `.tools/xcode-derived/Build/Products/Debug-iphonesimulator/CircleGuard.app`
- `.tools/ios-ui-*.xcresult`
- `androidApp/build/reports/androidTests/connected/debug/index.html`
- `androidApp/build/reports/lint-results-debug.html`
- `shared/build/reports/tests/jvmTest/index.html`

Run commands and fake-location walkthroughs are in `README.md`.
