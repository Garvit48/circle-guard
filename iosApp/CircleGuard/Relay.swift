import Foundation
import Security

enum Relay {
    static func request<T: Decodable>(_ type: T.Type, base: String, path: String, method: String = "GET", token: String = "", body: Data? = nil) async throws -> T {
        guard let url = URL(string: base + path), ["http", "https"].contains(url.scheme ?? ""), url.host != nil else {
            throw RelayError(status: 0, message: "Enter a valid relay URL, including http:// or https://.")
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let message = (try? JSONSerialization.jsonObject(with: data) as? [String: String])?["error"]
            throw RelayError(status: status, message: message ?? "Relay returned HTTP \(status).")
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
    static func json(_ values: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: values)
    }
}

enum ProfileVault {
    static func load(server: String) -> Profile? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "CircleGuard", kSecAttrAccount as String: server,
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(Profile.self, from: data)
    }
    static func save(_ profile: Profile, server: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "CircleGuard", kSecAttrAccount as String: server]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = try JSONEncoder().encode(profile)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(item as CFDictionary, nil)
        guard status == errSecSuccess else { throw RelayError(status: 0, message: "Could not securely save profile (\(status)).") }
    }
}
