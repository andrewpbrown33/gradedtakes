//  PrivateLink.swift
//  GradedTakes
//
//  The one secret in the app. A person's pages live at
//  https://gradedtakes.com/<token>/ where <token> is the unguessable folder
//  name publish.py generated for them (secrets.token_urlsafe(32): 43
//  characters of [A-Za-z0-9_-]). The token IS the lock, so this type is
//  handled like a password:
//    - it is stored in the Keychain (KeychainStore), never in UserDefaults
//    - it is never printed, logged, or put in an error message
//    - it is never the document URL of the web view (see PageSchemeHandler)
//    - anything sent to the push server carries `fingerprint`, a SHA-256
//      of the link, never the link itself
//
//  Accepted hosts: gradedtakes.com (and subdomains) and *.vercel.app for
//  preview deployments. Nothing else, so a pasted ESPN or Yahoo URL is
//  refused with a plain sentence rather than fetched.

import CryptoKit
import Foundation

struct PrivateLink: Equatable, Sendable {
    /// Lower-cased host, e.g. "gradedtakes.com".
    let host: String
    /// The unguessable folder name. Never displayed in full.
    let token: String

    /// Directory URL every page is relative to: https://host/token/
    var baseURL: URL {
        // Both parts are validated at parse time, so this cannot fail.
        URL(string: canonical)!
    }

    /// The canonical string form (always https, always a trailing slash).
    /// This exact string is what `fingerprint` hashes; a server that knows
    /// the token can recompute it as sha256("https://" + host + "/" + token + "/").
    var canonical: String { "https://\(host)/\(token)/" }

    /// SHA-256 of `canonical`, lower-case hex. Safe to send and to log.
    var fingerprint: String {
        SHA256.hash(data: Data(canonical.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    /// What Settings shows: the host and the last four characters only.
    var masked: String { "\(host)/\u{2026}\(token.suffix(4))/" }

    /// The page URL for a relative path such as "lineup-espn-1-week1.html".
    func url(forPath path: String) -> URL? {
        URL(string: path, relativeTo: baseURL)?.absoluteURL
    }

    // MARK: Parsing

    enum ParseError: Error, Equatable {
        case empty
        case notAURL
        case wrongHost
        case missingToken
        case weakToken

        /// In the product's voice. None of these echo the input back.
        var message: String {
            switch self {
            case .empty:
                return "Paste the link you were sent. It ends in home.html."
            case .notAURL:
                return "That doesn't read as a link. It starts with https://gradedtakes.com/ and has a long code after it."
            case .wrongHost:
                return "That link isn't a Graded Takes address. Yours starts with https://gradedtakes.com/."
            case .missingToken:
                return "The link is missing its private code - the long run of letters after gradedtakes.com/. Copy the whole thing."
            case .weakToken:
                return "The code in that link is too short to be one of ours. Copy the whole link, right up to home.html."
            }
        }
    }

    /// Token floor, matching publish.py: at least 24 characters of [A-Za-z0-9_-].
    private static let tokenMinimumLength = 24

    static func isAllowedHost(_ host: String) -> Bool {
        host == "gradedtakes.com"
            || host.hasSuffix(".gradedtakes.com")
            || host.hasSuffix(".vercel.app")
    }

    /// Accepts anything a person is likely to paste: with or without
    /// "https://", with or without "/home.html", with a fragment or a query,
    /// with surrounding whitespace. Rejects everything that is not one of
    /// this product's addresses.
    static func parse(_ raw: String) -> Result<PrivateLink, ParseError> {
        // A URL contains no whitespace; a paste from a message can (a wrapped
        // line, a trailing newline). Drop all of it rather than fail on it.
        var text = raw.filter { !$0.isWhitespace && !$0.isNewline }
        guard !text.isEmpty else { return .failure(.empty) }
        if !text.lowercased().hasPrefix("http://") && !text.lowercased().hasPrefix("https://") {
            text = "https://" + text
        }
        guard let components = URLComponents(string: text),
              let rawHost = components.host, !rawHost.isEmpty
        else { return .failure(.notAURL) }

        let host = rawHost.lowercased()
        guard isAllowedHost(host) else { return .failure(.wrongHost) }

        // The first non-empty path segment is the token; "home.html",
        // "index.html", "#league-espn-1" and so on are ignored.
        let segments = components.path.split(separator: "/", omittingEmptySubsequences: true)
        guard let first = segments.first else { return .failure(.missingToken) }
        let token = String(first)

        guard token.count >= tokenMinimumLength else {
            return .failure(token.count < 8 ? .missingToken : .weakToken)
        }
        guard token.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "-") }) else {
            return .failure(.notAURL)
        }
        return .success(PrivateLink(host: host, token: token))
    }

    /// True when `url` points inside this link's folder - such a navigation
    /// belongs in the app, not in Safari.
    func contains(_ url: URL) -> Bool {
        guard let h = url.host?.lowercased(), h == host else { return false }
        let segments = url.path.split(separator: "/", omittingEmptySubsequences: true)
        return segments.first.map(String.init) == token
    }

    /// The path of `url` relative to this link ("lineup-espn-1-week1.html"),
    /// with its fragment kept, or nil when the URL is not inside the link.
    func relativePath(of url: URL) -> String? {
        guard contains(url) else { return nil }
        let segments = url.path.split(separator: "/", omittingEmptySubsequences: true).dropFirst()
        var path = segments.joined(separator: "/")
        if path.isEmpty { path = "home.html" }
        if let fragment = url.fragment, !fragment.isEmpty { path += "#" + fragment }
        return path
    }
}
