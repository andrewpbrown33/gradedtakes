//  PlaceholderPage.swift
//  GradedTakes
//
//  What the web view shows when a page could not be fetched and there is
//  no saved copy. Self-contained HTML in the pages' own tokens (paper,
//  navy ink, one gold rule), so it reads as part of the product rather
//  than as an error screen. The native banner above it carries the
//  state; this page just says, in words, what is and is not here.

import Foundation

enum PlaceholderPage {
    static func html(path: String, offline: Bool, reason: String?) -> String {
        let name = Self.friendlyName(for: path)
        let lead: String
        let detail: String
        if offline {
            lead = "Nothing saved for \(name) yet."
            detail = "A phone can only keep a copy of a page it has fetched. Open this one once while you have a signal and it stays on your phone for the week."
        } else {
            lead = "Couldn't fetch \(name)."
            detail = escape(reason ?? "Your pages didn't answer.") + " Pull down to try again."
        }
        return """
        <!doctype html>
        <html lang="en"><head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="referrer" content="no-referrer">
        <title>Graded Takes</title>
        <style>
          html,body{margin:0;background:#F4F2EC;color:#101B33;font:16px/1.5 -apple-system,system-ui,sans-serif}
          @media (prefers-color-scheme:dark){html,body{background:#0D1730;color:#EAF0FA}}
          main{max-width:32rem;margin:0 auto;padding:3rem 1.5rem}
          .rule{width:2.5rem;height:3px;background:#F2B722;border-radius:2px;margin-bottom:1.25rem}
          h1{font-size:1.375rem;line-height:1.3;margin:0 0 .75rem;font-weight:600}
          p{margin:0 0 1rem}
          .muted{opacity:.72}
          a{color:inherit}
        </style></head>
        <body><main>
          <div class="rule"></div>
          <h1>\(escape(lead))</h1>
          <p>\(detail)</p>
          <p class="muted"><a href="home.html">Back to home</a></p>
        </main></body></html>
        """
    }

    /// "lineup-espn-1-week1.html" -> "the lineup page for espn-1".
    private static func friendlyName(for path: String) -> String {
        let file = path.split(separator: "#").first.map(String.init) ?? path
        if file == "home.html" { return "your home page" }
        if let destination = Destination.of(path: file) {
            let league = SiteMap.league(of: file).map { " for \($0)" } ?? ""
            return "the \(destination.title.lowercased()) page\(league)"
        }
        return "this page"
    }

    private static func escape(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }
}
