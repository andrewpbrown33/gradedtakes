//  Push.swift
//  GradedTakes
//
//  Native push is the feature a website cannot have: a Time Sensitive
//  alert that breaks through a Sunday-morning Focus mode ("your starter
//  was just ruled out, 90 minutes before kickoff"). This file owns
//  authorization, APNs registration, and handing the device token to the
//  Graded Takes server. Delivery callbacks live in AppDelegate.swift.
//
//  =====================================================================
//  THE SERVER CONTRACT
//  =====================================================================
//
//  1. Registration - the app POSTs on EVERY launch (Apple: forward the
//     token to your server every launch, never cache it):
//
//     POST https://gradedtakes.com/api/push/register      (configurable in Settings)
//     Content-Type: application/json
//     {
//       "token":            "a1b2c3...",     APNs device token, lower-case hex   REQUIRED
//       "link_fingerprint": "9f86d0...",     sha256("https://<host>/<token>/"), hex  REQUIRED
//       "host":             "gradedtakes.com",   the host in the reader's link
//       "environment":      "development" | "production",
//                           which APNs host the server must use for this token:
//                           api.sandbox.push.apple.com for Xcode-installed Debug
//                           builds, api.push.apple.com for TestFlight / App Store.
//                           Sending to the wrong one is 400 BadDeviceToken.
//       "platform":         "ios",
//       "app_version":      "1.0 (1)"
//     }
//     Any 2xx = registered. The private link itself is NEVER sent; the
//     server maps fingerprint -> person by hashing each token it knows the
//     same way (see PrivateLink.canonical).
//
//  2. The alert - what the server sends to APNs for a ruled-out starter:
//
//     HTTP/2 POST https://api.push.apple.com/3/device/<token>
//     headers:  apns-topic: com.gradedtakes.app
//               apns-push-type: alert
//               apns-priority: 10
//               apns-expiration: <unix seconds, e.g. kickoff>
//               apns-collapse-id: ruled-out-<player-id>      (optional)
//     body:
//     {
//       "aps": {
//         "alert": { "title": "Starter ruled out",
//                    "body":  "Breece Hall is OUT. Kickoff in 90 min. Open your lineup." },
//         "sound": "default",
//         "interruption-level": "time-sensitive",     <-- breaks through Focus.
//                                                     Needs the entitlement
//                                                     com.apple.developer.usernotifications.time-sensitive
//                                                     (GradedTakes.entitlements); no Apple approval.
//         "relevance-score": 1.0,
//         "thread-id": "week-1",
//         "badge": 1
//       },
//       "path":  "lineup-espn-1-week1.html",           page to open on tap (relative to the link)
//       "needs": { "count": 2, "headline": "2 calls need you",   optional: updates the widget
//                  "week": 1, "updated": "2026-09-13T14:12:00Z",  the moment the alert lands
//                  "path": "lineup-espn-1-week1.html" }
//     }
//
//  3. Silent pre-fetch (optional; UIBackgroundModes = remote-notification
//     is declared in Info.plist): warms the page before the visible alert.
//
//     headers:  apns-push-type: background, apns-priority: 5, apns-topic as above
//     body:     { "aps": { "content-available": 1 }, "path": "lineup-espn-1-week1.html" }
//     No alert, sound or badge keys. Apple throttles these to a few per hour.
//
//  4. Responses to act on: 410 Unregistered -> delete the token;
//     400 BadDeviceToken -> wrong environment (sandbox vs production).
//
//  =====================================================================
//
//  Authorization note. UNAuthorizationOptions.timeSensitive is deprecated
//  in the SDK ("Use time-sensitive entitlement" - UNUserNotificationCenter.h)
//  and is not requested. Time Sensitive is granted by the entitlement plus
//  the per-notification interruption level; the reader can switch it off
//  per app in Settings, which `timeSensitiveSetting` reports.

import Foundation
import Observation
import UIKit
import UserNotifications

@MainActor @Observable
final class PushRegistrar {
    static let defaultRegistrationURL = "https://gradedtakes.com/api/push/register"

    private(set) var authorization: UNAuthorizationStatus = .notDetermined
    private(set) var timeSensitive: UNNotificationSetting = .notSupported
    private(set) var lastRegisteredAt: Date?
    private(set) var lastRegistrationFailure: String?
    private(set) var isRegistering = false

    /// Where the device token is POSTed. Editable in Settings; not a secret.
    var registrationURLString: String {
        didSet { UserDefaults.standard.set(registrationURLString, forKey: Keys.registrationURL) }
    }

    /// The most recent APNs token, in memory only. Re-sent when the link
    /// appears (the token can arrive before the reader has pasted one).
    /// Readable so Settings can show it: the owner needs it for the test
    /// push (docs/TESTFLIGHT.md §8). Not a secret; per-phone, per-install.
    private(set) var deviceTokenHex: String?

    private enum Keys {
        static let registrationURL = "push.registrationURL"
        static let lastRegisteredAt = "push.lastRegisteredAt"
        static let asked = "push.asked"
    }

    init() {
        registrationURLString = UserDefaults.standard.string(forKey: Keys.registrationURL) ?? Self.defaultRegistrationURL
        lastRegisteredAt = UserDefaults.standard.object(forKey: Keys.lastRegisteredAt) as? Date
    }

    /// Has the system prompt been shown once? (We ask once, after the first
    /// page loads - not on the paste screen.)
    var hasAsked: Bool { UserDefaults.standard.bool(forKey: Keys.asked) }

    var registrationURL: URL? {
        let text = registrationURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: text), url.scheme?.lowercased() == "https", url.host != nil else { return nil }
        return url
    }

    // MARK: Authorization

    func refreshSettings() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        authorization = settings.authorizationStatus
        timeSensitive = settings.timeSensitiveSetting
    }

    /// Shows the system dialog (once) and registers with APNs on a yes.
    /// Options are alert/badge/sound only - see the note at the top.
    func requestAuthorization() async {
        UserDefaults.standard.set(true, forKey: Keys.asked)
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .badge, .sound])) ?? false
        await refreshSettings()
        if granted {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    /// Every launch: if the reader said yes at some point, ask APNs for a
    /// (possibly new) token. Cheap, and the only correct way to keep the
    /// server's token current.
    func registerIfAuthorized() async {
        await refreshSettings()
        switch authorization {
        case .authorized, .provisional, .ephemeral:
            UIApplication.shared.registerForRemoteNotifications()
        default:
            break
        }
    }

    // MARK: Token

    /// From AppDelegate. Keeps the token in memory and sends it if a link exists.
    func deviceTokenReceived(_ hex: String, link: PrivateLink?) {
        deviceTokenHex = hex
        if let link {
            Task { await self.send(link: link) }
        }
    }

    /// The link just appeared or changed: send the token we already have.
    func linkDidChange(_ link: PrivateLink?) {
        guard let link, deviceTokenHex != nil else { return }
        Task { await self.send(link: link) }
    }

    /// From AppDelegate when APNs registration failed (no network, or a
    /// build without the aps-environment entitlement). Retried next launch.
    func registrationFailed() {
        lastRegistrationFailure = "The phone couldn't get a notification token. It will try again next time the app opens."
    }

    private func send(link: PrivateLink) async {
        guard let token = deviceTokenHex, let url = registrationURL, !isRegistering else { return }
        isRegistering = true
        defer { isRegistering = false }
        do {
            try await PushRegistration.send(token: token, link: link, to: url)
            lastRegisteredAt = .now
            lastRegistrationFailure = nil
            UserDefaults.standard.set(lastRegisteredAt, forKey: Keys.lastRegisteredAt)
        } catch let failure as PushRegistration.Failure {
            lastRegistrationFailure = failure.message
        } catch {
            lastRegistrationFailure = PushRegistration.Failure.network.message
        }
    }

    // MARK: Settings deep link

    /// iOS Settings > Notifications > Graded Takes, where Time Sensitive lives.
    func openSystemSettings() {
        if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }

    /// The build's APNs environment, for the registration body. Debug
    /// builds installed by Xcode use a development profile (sandbox APNs);
    /// TestFlight and App Store builds use production.
    nonisolated static var environment: String {
        #if DEBUG
        return "development"
        #else
        return "production"
        #endif
    }
}

/// The one POST. Separate so it has no state and can be called from anywhere.
enum PushRegistration {
    enum Failure: Error, Sendable {
        case badURL
        case network
        case status(Int)

        var message: String {
            switch self {
            case .badURL: return "The registration address in Settings isn't a valid https:// link."
            case .network: return "Couldn't reach the notification server. It will try again next time the app opens."
            case .status(let code): return "The notification server answered with an error (\(code)). It will try again next time the app opens."
            }
        }
    }

    struct Body: Encodable {
        let token: String
        let linkFingerprint: String
        let host: String
        let environment: String
        let platform: String
        let appVersion: String

        enum CodingKeys: String, CodingKey {
            case token
            case linkFingerprint = "link_fingerprint"
            case host, environment, platform
            case appVersion = "app_version"
        }
    }

    static func send(token: String, link: PrivateLink, to url: URL) async throws {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "0"
        let build = info?["CFBundleVersion"] as? String ?? "0"
        let body = Body(
            token: token,
            linkFingerprint: link.fingerprint,
            host: link.host,
            environment: PushRegistrar.environment,
            platform: "ios",
            appVersion: "\(version) (\(build))"
        )
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONEncoder().encode(body)

        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        let session = URLSession(configuration: config)
        let response: URLResponse
        do {
            (_, response) = try await session.data(for: request)
        } catch {
            throw Failure.network
        }
        guard let http = response as? HTTPURLResponse else { throw Failure.network }
        guard (200..<300).contains(http.statusCode) else { throw Failure.status(http.statusCode) }
    }
}
