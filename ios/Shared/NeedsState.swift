//  NeedsState.swift
//  Compiled into BOTH targets (app and widget) via ios/Shared.
//
//  THE WIDGET CONTRACT. The widget runs as a separate process and cannot
//  see the app's sandbox, the Keychain item, or the network; the only thing
//  the two share is the App Group container (WWDC26 277: "you will need to
//  use a shared container in an app group"). The app writes ONE small JSON
//  file there after each successful refresh; the widget only ever reads it.
//
//  The private link is never written here. The widget does not need it, so
//  it never has it.
//
//  ---------------------------------------------------------------------
//  1. What the PAGES publish (server side), fetched by the app:
//
//     GET https://gradedtakes.com/<token>/needs.json
//     {
//       "schema":   "gradedtakes.needs/1",          optional
//       "count":    2,                              required, integer >= 0
//       "headline": "2 calls need you",             required, one short line
//       "week":     1,                              optional, integer
//       "updated":  "2026-09-13T14:12:00Z",         optional, ISO-8601 UTC
//       "path":     "lineup-espn-1-week1.html"      optional, page to open on tap
//     }
//
//     Absent (404) means "nothing to say": the app clears the shared file
//     and the widget shows "Open the app". A fetch that fails for network
//     reasons leaves the last good state in place; the widget then shows
//     its "as of" line so a stale count is never presented as current.
//
//  2. What the APP writes to the App Group container (this file):
//
//     <group container>/needs.json  = NeedsState below, JSON, ISO-8601 dates
//     `fetchedAt` is the moment the app fetched it; that is the timestamp
//     the widget shows when the state is old. We put the date INSIDE the
//     JSON on purpose: reading a file's modification date is a
//     "required reason" API (NSPrivacyAccessedAPICategoryFileTimestamp);
//     a date inside the JSON is not.
//  ---------------------------------------------------------------------

import Foundation
import WidgetKit

/// The state the widget renders. Codable for the shared file; Sendable so it
/// can cross from the app's actors to the widget's timeline provider.
struct NeedsState: Codable, Sendable, Equatable {
    /// How many calls need the reader before kickoff. 0 is a real answer.
    var count: Int
    /// One line, in the product's voice: "2 calls need you".
    var headline: String
    /// The NFL week the count refers to, when the pages said.
    var week: Int?
    /// The server's own timestamp for the count, when the pages said.
    var updated: Date?
    /// The page a tap on the widget should open (relative to the link).
    var path: String?
    /// When the app fetched this state. Source of truth for "as of".
    var fetchedAt: Date

    /// Older than this and the widget says "as of <time>" under the count.
    static let staleAfter: TimeInterval = 6 * 60 * 60

    var isStale: Bool { Date.now.timeIntervalSince(fetchedAt) > Self.staleAfter }
}

/// Reads and writes the shared file. No instance, no state: every call goes
/// to disk, which is what a widget wants (a fresh read per timeline).
enum NeedsStore {
    /// Must match `com.apple.security.application-groups` in BOTH
    /// entitlements files (GradedTakes.entitlements, GradedTakesWidget.entitlements).
    static let appGroupID = "group.com.gradedtakes.app"

    /// The widget's `kind`. The app reloads exactly this timeline after a write.
    static let widgetKind = "com.gradedtakes.app.needs"

    static let fileName = "needs.json"

    /// The deep link the widget opens. Handled by `.onOpenURL` in the app.
    static let widgetDeepLink = URL(string: "gradedtakes://needs")!

    /// nil only when the App Group entitlement is missing from the target,
    /// which is a signing/configuration error, not a runtime condition.
    static var fileURL: URL? {
        FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: appGroupID)?
            .appendingPathComponent(fileName, isDirectory: false)
    }

    static func read() -> NeedsState? {
        guard let url = fileURL, let data = try? Data(contentsOf: url) else { return nil }
        return try? decoder().decode(NeedsState.self, from: data)
    }

    /// App side. Writes atomically, then asks WidgetKit to re-render. A
    /// reload while the app is in the foreground does not count against
    /// the widget's daily budget (WWDC26 277).
    static func write(_ state: NeedsState) throws {
        guard let url = fileURL else { throw NeedsStoreError.noAppGroup }
        let data = try encoder().encode(state)
        try data.write(to: url, options: .atomic)
        WidgetCenter.shared.reloadTimelines(ofKind: widgetKind)
    }

    /// App side. Removes the state (the link was forgotten, or the pages
    /// no longer publish needs.json) and re-renders the "Open the app" face.
    static func clear() {
        if let url = fileURL {
            try? FileManager.default.removeItem(at: url)
        }
        WidgetCenter.shared.reloadTimelines(ofKind: widgetKind)
    }

    // JSON coders are built per call rather than held in a static: a shared
    // mutable coder is not concurrency-safe under Swift 6.
    private static func encoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.sortedKeys]
        return e
    }

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }
}

enum NeedsStoreError: Error {
    case noAppGroup
}
