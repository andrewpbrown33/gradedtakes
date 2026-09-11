//  PageScheme.swift
//  GradedTakes
//
//  The web view never loads https://gradedtakes.com/<token>/... directly.
//  It loads gradedtakes-pages://pages/<path>, a private scheme served by
//  PageSchemeHandler from the on-device store (which PageService fills
//  from the network). Three reasons, all from the research brief:
//
//   1. Referrer. WebKit has no WKWebView API for referrer policy (WebKit
//      bug 206521, open since 2020). A document whose URL never contains
//      the token cannot leak the token in a Referer header, whatever a
//      page does. UIApplication.open / SFSafariViewController start a fresh
//      top-level navigation from native code and carry no Referer at all.
//   2. History. WebKit writes document URLs into its on-disk cache and
//      history; with this scheme those files contain "pages/home.html",
//      not the secret.
//   3. A stable origin. localStorage (the pages' theme / density / quiet
//      prefs from engine/prefs.py) persists across launches and across the
//      online and offline cases, because the origin is always the same.
//      file:// would give every page a different origin.
//
//  The scheme must not be http, https or file (WebKit refuses to hand
//  those to a handler). Relative links inside a page - "lineup-espn-1-week1.html",
//  "home.html#league-espn-1" - resolve to this scheme automatically.

import Foundation

enum PageScheme {
    static let scheme = "gradedtakes-pages"
    static let host = "pages"
    static let homePath = "home.html"

    /// gradedtakes-pages://pages/<path>  (path may carry a #fragment).
    static func url(for path: String) -> URL {
        let parts = path.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
        let file = parts.first.map(String.init) ?? homePath
        var components = URLComponents()
        components.scheme = scheme
        components.host = host
        components.path = "/" + (file.isEmpty ? homePath : file)
        if parts.count > 1 { components.fragment = String(parts[1]) }
        return components.url ?? URL(string: "\(scheme)://\(host)/\(homePath)")!
    }

    /// The store key for a scheme URL: "lineup-espn-1-week1.html",
    /// "icons/icon.svg". nil for anything that is not a plain relative path
    /// (traversal, absolute, empty segments), which the handler answers 404.
    static func path(from url: URL) -> String? {
        guard url.scheme?.lowercased() == scheme else { return nil }
        let segments = url.path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        if segments.isEmpty { return homePath }
        for segment in segments {
            guard segment != "..", segment != ".",
                  segment.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || ".-_".contains($0)) })
            else { return nil }
        }
        return segments.joined(separator: "/")
    }

    static func isSchemeURL(_ url: URL) -> Bool {
        url.scheme?.lowercased() == scheme
    }
}
