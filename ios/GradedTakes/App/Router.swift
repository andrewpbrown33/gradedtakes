//  Router.swift
//  GradedTakes
//
//  Where the web view should be, and where it is. Two properties on purpose:
//    `request`     a command INTO the web view (toolbar tap, notification
//                  tap, widget deep link). New id every time, so tapping
//                  "Lineup" while already on the lineup reloads it.
//    `currentPath` what the web view reports it is showing (in-page links,
//                  back gestures). The toolbar highlights from this.
//
//  Deep links handled here (CFBundleURLSchemes = gradedtakes):
//    gradedtakes://home                    the home page
//    gradedtakes://needs                   the page needs.json named, else home
//    gradedtakes://open?path=<page.html>   a specific page (used by pushes too)

import Foundation
import Observation

struct NavigationRequest: Equatable, Sendable {
    let id: UUID
    let path: String

    init(path: String) {
        id = UUID()
        self.path = path
    }
}

/// A link the app decided to open outside the web view.
struct ExternalLink: Identifiable, Equatable, Sendable {
    let id = UUID()
    let url: URL
}

@MainActor @Observable
final class Router {
    private(set) var request = NavigationRequest(path: PageScheme.homePath)
    private(set) var currentPath = PageScheme.homePath

    /// The league the toolbar buttons open, when there is more than one.
    /// Not a secret; a plain preference.
    var selectedLeague: String? {
        didSet { UserDefaults.standard.set(selectedLeague, forKey: Self.leagueKey) }
    }

    /// Set when an http(s) link must open in Safari (view controller).
    var safariLink: ExternalLink?

    private static let leagueKey = "selectedLeague"

    init() {
        selectedLeague = UserDefaults.standard.string(forKey: Self.leagueKey)
    }

    /// Navigate the web view to a page path (relative to the link).
    func go(to path: String) {
        guard let clean = Self.sanitize(path) else { return }
        request = NavigationRequest(path: clean)
    }

    /// Navigate to a toolbar destination using the current site map.
    func go(to destination: Destination, in siteMap: SiteMap) {
        let league = selectedLeague ?? siteMap.leagues.first
        let path = siteMap.path(for: destination, league: league) ?? PageScheme.homePath
        go(to: path)
    }

    /// The league menu: remember the choice and re-open the same destination
    /// for that league. (In-page navigation updates `selectedLeague` through
    /// `didShow` without re-navigating.)
    func selectLeague(_ league: String, in siteMap: SiteMap) {
        guard league != selectedLeague else { return }
        selectedLeague = league
        if let destination = currentDestination, destination != .home {
            go(to: destination, in: siteMap)
        }
    }

    /// The web view reports where it is.
    func didShow(path: String) {
        currentPath = path
        if let league = SiteMap.league(of: path), league != selectedLeague {
            selectedLeague = league
        }
    }

    var currentDestination: Destination? {
        Destination.of(path: currentPath)
    }

    /// `.onOpenURL` entry point for gradedtakes:// links.
    func handle(_ url: URL, needs: NeedsState?) {
        guard url.scheme?.lowercased() == "gradedtakes" else { return }
        switch url.host?.lowercased() {
        case "open":
            let path = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "path" }?.value
            go(to: path ?? PageScheme.homePath)
        case "needs", "calls":
            go(to: needs?.path ?? PageScheme.homePath)
        default:
            go(to: PageScheme.homePath)
        }
    }

    /// A page path from outside (push payload, deep link) is trusted only
    /// after it proves to be a plain relative page name with an optional
    /// fragment. Anything else is dropped.
    static func sanitize(_ path: String) -> String? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return PageScheme.homePath }
        let parts = trimmed.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
        let file = String(parts[0])
        guard SiteMap.isPageName(file) else { return nil }
        if parts.count > 1 {
            let fragment = String(parts[1])
            guard fragment.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || "-_.".contains($0)) }) else { return file }
            return file + "#" + fragment
        }
        return file
    }
}
