import Foundation

struct Profile: Codable {
    let id: String
    let name: String
    let token: String
}
struct Member: Codable, Identifiable {
    let id: String
    let name: String
    let state: String
    let mode: String
    let updatedAt: Double
    let distance: Double?
}
struct TrackingGroup: Codable, Identifiable {
    let id: String
    let name: String
    let code: String
    let ownerId: String
    let latitude: Double
    let longitude: Double
    let radius: Double
    let version: Int
    let members: [Member]
}
struct ExitEvent: Codable, Identifiable {
    let id: Int
    let groupId: String
    let actorId: String
    let title: String
    let body: String
    let simulated: Int
    let createdAt: Double
}
struct GroupsResponse: Decodable { let groups: [TrackingGroup] }
struct EventsResponse: Decodable { let events: [ExitEvent]; let cursor: Int }
struct HealthResponse: Decodable { let status: String; let apns: Bool }
struct LocationResponse: Decodable { let duplicate: Bool; let exits: Int }
struct OKResponse: Decodable { let ok: Bool }
struct LocationReport: Codable, Identifiable {
    var id: String { requestId }
    let latitude: Double
    let longitude: Double
    let accuracy: Double
    let observedAt: Double
    let requestId: String
    let simulated: Bool
    let groupId: String?
}
struct RelayError: LocalizedError {
    let status: Int
    let message: String
    var errorDescription: String? { message }
}
