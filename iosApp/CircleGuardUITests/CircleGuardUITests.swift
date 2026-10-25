import XCTest

final class CircleGuardUITests: XCTestCase {
    func request(_ path: String, _ values: [String: Any], token: String = "") async throws -> [String: Any] {
        var req = URLRequest(url: URL(string: "http://127.0.0.1:8787" + path)!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.httpBody = try JSONSerialization.data(withJSONObject: values)
        let (data, response) = try await URLSession.shared.data(for: req)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @MainActor
    func testGroupReceivesSimulatedExitFromAnotherMember() async throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--uitest"]
        app.launch()
        addUIInterruptionMonitor(withDescription: "Notifications") { alert in
            if alert.buttons["Allow"].exists { alert.buttons["Allow"].tap(); return true }
            return false
        }
        let name = app.textFields["profileName"]
        XCTAssertTrue(name.waitForExistence(timeout: 10))
        name.tap()
        name.typeText("UI Observer")
        app.buttons["connect"].tap()
        let create = app.buttons["createGroup"]
        XCTAssertTrue(create.waitForExistence(timeout: 20), app.debugDescription)
        app.tap()
        create.tap()
        app.buttons["saveGroup"].tap()
        let codeLabel = app.staticTexts["inviteCode"]
        XCTAssertTrue(codeLabel.waitForExistence(timeout: 15))
        let code = codeLabel.label
        let actor = try await request("/users", ["name": "UI Walker"])
        let token = try XCTUnwrap(actor["token"] as? String)
        let joined = try await request("/join", ["code": code], token: token)
        let groupID = try XCTUnwrap(joined["groupId"] as? String)
        for lon in [-122.009, -121.99, -121.99] {
            _ = try await request("/locations", ["latitude": 37.3349, "longitude": lon, "accuracy": 5,
                "simulated": true, "groupId": groupID, "observedAt": Date().timeIntervalSince1970, "requestId": UUID().uuidString], token: token)
        }
        let alert = app.staticTexts["UI Walker left My circle’s safe area."]
        for _ in 0..<5 {
            if alert.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(alert.waitForExistence(timeout: 15))
        XCTAssertTrue(alert.isHittable, "The received alert must be visibly on screen")
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Simulated group exit alert"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}
