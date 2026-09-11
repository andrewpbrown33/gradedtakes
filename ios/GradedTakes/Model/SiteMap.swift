//  SiteMap.swift
//  GradedTakes
//
//  Which pages exist this week, and which one each native toolbar button
//  opens. The publisher writes heartbeat.json beside the pages
//  (schema warroom.publish.heartbeat/2) with `page_files`, `week` and
//  `published_at`; that is the primary source. When it is not available
//  yet, the links inside the cached home.html say the same thing, because
//  the home page links to every page of every league.
//
//  Page file names follow publish.py exactly:
//    home.html, sources.html, install.html
//    lineup-<league>-week<N>.html   board-<league>-week<N>.html
//    digest-<league>-week<N>.html   tradedesk-<league>-week<N>.html
//  "Ledger" in the pages' own nav is the digest page.

import Foundation

/// The five native destinations, in toolbar order.
enum Destination: String, CaseIterable, Identifiable, Sendable {
    case home, lineup, board, ledger, tradeDesk

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: return "Home"
        case .lineup: return "Lineup"
        case .board: return "Board"
        case .ledger: return "Ledger"
        case .tradeDesk: return "Trade Desk"
        }
    }

    /// SF Symbols, one weight, no colour of their own.
    var symbol: String {
        switch self {
        case .home: return "house"
        case .lineup: return "list.number"
        case .board: return "square.grid.3x3"
        case .ledger: return "book.closed"
        case .tradeDesk: return "arrow.left.arrow.right"
        }
    }

    /// The file-name prefix the destination's pages share.
    var pagePrefix: String {
        switch self {
        case .home: return "home"
        case .lineup: return "lineup-"
        case .board: return "board-"
        case .ledger: return "digest-"
        case .tradeDesk: return "tradedesk-"
        }
    }

    /// Which destination a page path belongs to (nil for sources.html etc.).
    static func of(path: String) -> Destination? {
        let name = path.split(separator: "#").first.map(String.init) ?? path
        if name == "home.html" || name.isEmpty { return .home }
        return allCases.first { $0 != .home && name.hasPrefix($0.pagePrefix) }
    }
}

struct SiteMap: Equatable, Sendable {
    /// The week the publisher stamped, when known.
    var week: Int?
    /// When the publisher wrote the set, when known.
    var publishedAt: Date?
    /// Every page file name, in publisher order.
    var pages: [String] = []

    /// League ids in the order their pages first appear ("espn-1", "yahoo-main").
    var leagues: [String] {
        var seen: [String] = []
        for page in pages {
            if let league = Self.parse(page)?.league, !seen.contains(league) {
                seen.append(league)
            }
        }
        return seen
    }

    var isEmpty: Bool { pages.isEmpty }

    /// The page for a destination, preferring `league`, else the first league
    /// that has one. Home is always home.html.
    func path(for destination: Destination, league: String?) -> String? {
        if destination == .home { return "home.html" }
        let candidates = pages.filter { $0.hasPrefix(destination.pagePrefix) }
        if let league, let match = candidates.first(where: { Self.parse($0)?.league == league }) {
            return match
        }
        return candidates.first
    }

    /// The league a page belongs to, if it is a per-league page.
    static func league(of path: String) -> String? {
        parse(path)?.league
    }

    /// Week number embedded in a per-league page name, if any.
    static func week(of path: String) -> Int? {
        parse(path)?.week
    }

    // MARK: Building

    /// From heartbeat.json (warroom.publish.heartbeat/2).
    static func fromHeartbeat(_ data: Data) -> SiteMap? {
        struct Heartbeat: Decodable {
            let week: Int?
            let pageFiles: [String]?
            let publishedAt: String?
            enum CodingKeys: String, CodingKey {
                case week
                case pageFiles = "page_files"
                case publishedAt = "published_at"
            }
        }
        guard let hb = try? JSONDecoder().decode(Heartbeat.self, from: data),
              let files = hb.pageFiles, !files.isEmpty
        else { return nil }
        return SiteMap(
            week: hb.week,
            publishedAt: hb.publishedAt.flatMap(ISO8601.parse),
            pages: files.filter(isPageName)
        )
    }

    /// From the links inside a rendered home.html - the fallback when the
    /// heartbeat has not been fetched yet. The home page links to most
    /// pages but not necessarily all (verified: the week-1 home page has no
    /// link to the Yahoo lineup), so for every league and week it mentions
    /// the four per-league pages are added by name. publish.py renders all
    /// four for every league, and a page that does not exist answers 404
    /// and shows the placeholder rather than another league's page.
    static func fromHomePage(_ data: Data) -> SiteMap? {
        let html = String(decoding: data, as: UTF8.self)
        var names: [String] = ["home.html"]
        for match in html.matches(of: #/href="([A-Za-z0-9._-]+\.html)(?:[#?][^"]*)?"/#) {
            let name = String(match.output.1)
            if isPageName(name), !names.contains(name) { names.append(name) }
        }
        guard names.count > 1 else { return nil }
        for parsed in names.compactMap(parse) {
            for kind in ["lineup", "board", "digest", "tradedesk"] {
                let sibling = "\(kind)-\(parsed.league)-week\(parsed.week).html"
                if !names.contains(sibling) { names.append(sibling) }
            }
        }
        let week = names.compactMap(Self.week(of:)).max()
        return SiteMap(week: week, publishedAt: nil, pages: names)
    }

    // MARK: Parsing page names

    private struct Parsed { let kind: String; let league: String; let week: Int }

    private static func parse(_ name: String) -> Parsed? {
        guard let match = name.wholeMatch(of: #/^(lineup|board|digest|tradedesk)-(.+)-week(\d+)\.html$/#),
              let week = Int(match.output.3)
        else { return nil }
        return Parsed(kind: String(match.output.1), league: String(match.output.2), week: week)
    }

    /// Page file names are plain: letters, digits, dot, dash, underscore.
    static func isPageName(_ name: String) -> Bool {
        name.hasSuffix(".html")
            && !name.contains("/")
            && !name.contains("..")
            && name.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "." || $0 == "-" || $0 == "_") }
    }
}

/// ISO-8601 parsing that accepts both "2026-09-13T14:12:00Z" and the
/// fractional-seconds form. Foundation's format style is a value type, so
/// this is safe to call from any actor.
enum ISO8601 {
    static func parse(_ text: String) -> Date? {
        if let date = try? Date.ISO8601FormatStyle().parse(text) { return date }
        return try? Date.ISO8601FormatStyle(includingFractionalSeconds: true).parse(text)
    }
}
