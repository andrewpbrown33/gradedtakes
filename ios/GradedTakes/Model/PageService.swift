//  PageService.swift
//  GradedTakes
//
//  "Which copy of this page do I show, and what do I tell the reader about
//  it?" - the one place that decision is made. The scheme handler asks
//  `serve(path:)` for every document the web view loads; the answer is the
//  bytes plus a `ServedPage` the banner renders from.
//
//  Policy, in order:
//    1. Online: ask the server, revalidating with the ETag of the copy on
//       disk. 200 -> store it, show it, mark LIVE. 304 -> the copy on disk
//       is current, show it, mark LIVE (verified now).
//    2. Any failure, or no network path: show the copy on disk, mark SAVED
//       with the date it was fetched. The banner is on.
//    3. No copy on disk: a small placeholder page that says so. The banner
//       is on and says nothing is saved.
//
//  The honesty rule (product requirement, docs/APPSTORE.md and install.html:
//  "War Room will never show you a saved page as if it were live"): every
//  path through this file that shows a saved copy also publishes the date
//  it was fetched. There is no code path that shows a saved page silently.

import Foundation
import Observation

@MainActor @Observable
final class PageService {
    enum Source: Equatable, Sendable {
        /// Fetched or verified against the server at this moment.
        case live(Date)
        /// The copy on disk, fetched at this date; the server was not reached.
        case saved(Date)
        /// Nothing on disk and the server was not reached.
        case missing
    }

    struct ServedPage: Equatable, Sendable {
        let path: String
        let source: Source
        let week: Int?
    }

    /// What the scheme handler hands to WebKit.
    struct Reply: Sendable {
        let status: Int
        let mimeType: String
        let data: Data
    }

    /// The page currently on screen, as served. nil before the first load.
    private(set) var served: ServedPage?

    /// Pages this week, for the toolbar. Empty until the first home load
    /// (or restored from the cache at launch).
    private(set) var siteMap = SiteMap()

    /// The last network failure for a page load. nil after any success.
    private(set) var lastFailure: PageFetcher.Failure?

    /// Mirror of the widget's shared state, for Settings and deep links.
    private(set) var needs: NeedsState?

    /// Set by the web view's coordinator while a navigation is in flight.
    var isLoading = false

    private let links: LinkStore
    private let connectivity: Connectivity
    private let store: OfflineStore
    private let fetcher = PageFetcher()
    private var lastNeedsRefresh: Date?
    private var lastSiteMapRefresh: Date?

    /// Side refreshes (needs.json, heartbeat.json) at most this often.
    private let sideRefreshInterval: TimeInterval = 60

    init(links: LinkStore, connectivity: Connectivity, store: OfflineStore) {
        self.links = links
        self.connectivity = connectivity
        self.store = store
        needs = NeedsStore.read()
        Task { await self.restoreSiteMapFromCache() }
    }

    // MARK: Serving

    /// Called by PageSchemeHandler for every request the web view makes.
    func serve(path: String) async -> Reply {
        let isPage = path.lowercased().hasSuffix(".html")
        let mime = Self.mimeType(for: path)

        guard let base = links.link?.baseURL else {
            // No link: the onboarding screen is up; the web view is not.
            return Reply(status: 404, mimeType: "text/html", data: Data())
        }

        let cached = await store.read(path)
        var data: Data?
        var source: Source?

        if connectivity.isOnline {
            do {
                let outcome = try await fetcher.fetch(base: base, path: path, etag: cached?.etag)
                let now = Date.now
                switch outcome {
                case .fresh(let fresh, let etag):
                    try? await store.write(path, data: fresh, etag: etag, fetchedAt: now)
                    data = fresh
                    source = .live(now)
                case .notModified:
                    if let cached {
                        await store.markVerified(path, at: now)
                        data = cached.data
                        source = .live(now)
                    } else if case .fresh(let fresh, let etag) = try await fetcher.fetch(base: base, path: path, etag: nil) {
                        // A 304 with nothing on disk cannot happen (we only send
                        // If-None-Match with a copy), but a stray one is handled.
                        try? await store.write(path, data: fresh, etag: etag, fetchedAt: now)
                        data = fresh
                        source = .live(now)
                    }
                }
                if isPage { lastFailure = nil }
            } catch let failure as PageFetcher.Failure {
                if isPage { lastFailure = failure }
            } catch {
                if isPage { lastFailure = .network }
            }
        } else if isPage {
            lastFailure = .offline
        }

        if data == nil, let cached {
            data = cached.data
            source = .saved(cached.fetchedAt)
        }

        guard isPage else {
            if let data { return Reply(status: 200, mimeType: mime, data: data) }
            return Reply(status: 404, mimeType: mime, data: Data())
        }

        let week = siteMap.week ?? SiteMap.week(of: path)
        if let data, let source {
            served = ServedPage(path: path, source: source, week: week)
            if case .live = source {
                afterLiveLoad(path: path, data: data)
            } else if siteMap.isEmpty, path == "home.html", let map = SiteMap.fromHomePage(data) {
                siteMap = map
            }
            return Reply(status: 200, mimeType: "text/html", data: data)
        }

        served = ServedPage(path: path, source: .missing, week: week)
        let html = PlaceholderPage.html(
            path: path,
            offline: !connectivity.isOnline || lastFailure == .offline,
            reason: lastFailure?.message
        )
        return Reply(status: 200, mimeType: "text/html", data: Data(html.utf8))
    }

    /// The silent-push warm-up (AppDelegate): fetch `path` and store it on
    /// disk exactly as `serve(path:)` would, but publish nothing. `served`,
    /// `lastFailure` and `siteMap` describe the page ON SCREEN; a background
    /// push for some other page must not remove or rewrite the honesty
    /// banner over whatever the reader is looking at.
    func prefetch(path: String) async {
        guard let base = links.link?.baseURL, connectivity.isOnline else { return }
        let cached = await store.read(path)
        do {
            switch try await fetcher.fetch(base: base, path: path, etag: cached?.etag) {
            case .fresh(let fresh, let etag):
                try? await store.write(path, data: fresh, etag: etag, fetchedAt: .now)
            case .notModified:
                if cached != nil { await store.markVerified(path, at: .now) }
            }
        } catch {
            // Background only: nothing on screen to tell, and the next
            // foreground load reports its own failure.
        }
    }

    /// Something fresh just arrived: keep the site map and the widget current.
    private func afterLiveLoad(path: String, data: Data) {
        if path == "home.html", siteMap.isEmpty, let map = SiteMap.fromHomePage(data) {
            siteMap = map
        }
        Task { await self.refreshSiteMap() }
        Task { await self.refreshNeeds() }
    }

    // MARK: Site map

    /// Before any network: the last heartbeat or home page on disk.
    private func restoreSiteMapFromCache() async {
        guard siteMap.isEmpty else { return }
        if let hb = await store.read("heartbeat.json"), let map = SiteMap.fromHeartbeat(hb.data) {
            siteMap = map
        } else if let home = await store.read("home.html"), let map = SiteMap.fromHomePage(home.data) {
            siteMap = map
        }
    }

    /// heartbeat.json from the publisher, throttled. Stored on disk like a
    /// page so the map survives a launch with no signal.
    func refreshSiteMap(force: Bool = false) async {
        if !force, let last = lastSiteMapRefresh, Date.now.timeIntervalSince(last) < sideRefreshInterval { return }
        guard connectivity.isOnline, let base = links.link?.baseURL else { return }
        lastSiteMapRefresh = .now
        let cached = await store.read("heartbeat.json")
        do {
            switch try await fetcher.fetch(base: base, path: "heartbeat.json", etag: cached?.etag) {
            case .fresh(let data, let etag):
                if let map = SiteMap.fromHeartbeat(data) {
                    try? await store.write("heartbeat.json", data: data, etag: etag, fetchedAt: .now)
                    siteMap = map
                }
            case .notModified:
                if let cached, let map = SiteMap.fromHeartbeat(cached.data) { siteMap = map }
            }
        } catch {
            // Not fatal: the home page's own links already filled the map.
        }
    }

    // MARK: needs.json -> widget

    /// Fetches <link>/needs.json and writes the widget's shared state.
    /// See NeedsState.swift for the contract. Throttled unless forced.
    func refreshNeeds(force: Bool = false) async {
        if !force, let last = lastNeedsRefresh, Date.now.timeIntervalSince(last) < sideRefreshInterval { return }
        guard connectivity.isOnline, let base = links.link?.baseURL else { return }
        lastNeedsRefresh = .now
        do {
            switch try await fetcher.fetch(base: base, path: "needs.json", etag: nil) {
            case .fresh(let data, _):
                if let state = Self.decodeNeeds(data, fetchedAt: .now) {
                    try? NeedsStore.write(state)
                    needs = state
                }
            case .notModified:
                break
            }
        } catch PageFetcher.Failure.notFound {
            // The pages publish nothing to say: the widget shows "Open the app".
            NeedsStore.clear()
            needs = nil
        } catch {
            // Network trouble: keep the last good state; the widget dates it.
        }
    }

    /// Applies a `needs` object carried inside a push payload (as JSON
    /// bytes, which are Sendable), so the widget updates the moment the
    /// alert lands, before the app is even opened.
    func applyNeeds(json data: Data) {
        guard let state = Self.decodeNeeds(data, fetchedAt: .now) else { return }
        try? NeedsStore.write(state)
        needs = state
    }

    /// Tolerant decode of the server's needs.json.
    static func decodeNeeds(_ data: Data, fetchedAt: Date) -> NeedsState? {
        struct Payload: Decodable {
            let count: Int?
            let headline: String?
            let week: Int?
            let updated: String?
            let path: String?
        }
        guard let p = try? JSONDecoder().decode(Payload.self, from: data) else { return nil }
        let count = max(0, p.count ?? 0)
        let headline = (p.headline ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let path = p.path.flatMap { SiteMap.isPageName($0) ? $0 : nil }
        return NeedsState(
            count: count,
            headline: headline.isEmpty ? Self.defaultHeadline(count: count) : headline,
            week: p.week,
            updated: p.updated.flatMap(ISO8601.parse),
            path: path,
            fetchedAt: fetchedAt
        )
    }

    static func defaultHeadline(count: Int) -> String {
        switch count {
        case 0: return "Nothing needs you"
        case 1: return "1 call needs you"
        default: return "\(count) calls need you"
        }
    }

    // MARK: Cache

    func cacheSummary() async -> OfflineStore.Summary {
        await store.summary()
    }

    /// Everything on disk and in the widget, gone. The link was replaced
    /// or forgotten, or the reader asked.
    func clearCache() async {
        try? await store.clear()
        NeedsStore.clear()
        needs = nil
        siteMap = SiteMap()
        served = nil
        lastFailure = nil
        lastNeedsRefresh = nil
        lastSiteMapRefresh = nil
    }

    // MARK: MIME

    static func mimeType(for path: String) -> String {
        let name = path.split(separator: "#").first.map(String.init) ?? path
        switch (name as NSString).pathExtension.lowercased() {
        case "html", "htm": return "text/html"
        case "json": return "application/json"
        case "webmanifest": return "application/manifest+json"
        case "svg": return "image/svg+xml"
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "js": return "text/javascript"
        case "css": return "text/css"
        case "txt": return "text/plain"
        default: return "application/octet-stream"
        }
    }
}
