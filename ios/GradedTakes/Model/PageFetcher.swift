//  PageFetcher.swift
//  GradedTakes
//
//  The only code that puts the private link on the wire. One URLSession,
//  ephemeral (nothing about the link is written to a cookie jar or a URL
//  cache on disk), no redirects off the link's host, ETag revalidation so
//  a weekly 4 MB set of pages costs bytes only when it changed.
//
//  Errors are mapped to a closed set that carries NO URL: URLError's
//  description can include the failing URL, and the failing URL contains
//  the token. Nothing in this file prints.

import Foundation

struct PageFetcher: Sendable {
    enum Outcome: Sendable {
        /// A new copy (200), with the ETag the server sent, if any.
        case fresh(Data, etag: String?)
        /// The server confirmed the copy we have is current (304).
        case notModified
    }

    enum Failure: Error, Sendable, Equatable {
        /// No route to the host, connection lost, or data disallowed.
        case offline
        /// The request took longer than `timeout`.
        case timedOut
        /// Any other transport failure (TLS, DNS, reset).
        case network
        /// The link's page is not there (404). Wrong or rotated token, or a
        /// page that does not exist this week.
        case notFound
        /// The server answered with a status we do not handle.
        case status(Int)
        /// The response came from a different host than the link - a login
        /// wall (Cloudflare Access) or a redirect the app must not follow.
        case redirectedOffHost
        /// A .html path came back as something other than HTML.
        case notAPage

        /// In the product's voice, for the banner and Settings.
        var message: String {
            switch self {
            case .offline: return "No signal."
            case .timedOut: return "Your pages took too long to answer."
            case .network: return "Couldn't reach your pages."
            case .notFound: return "Your pages weren't found at that link. If it was re-issued, paste the new one in Settings."
            case .status(let code): return "Your pages answered with an error (\(code))."
            case .redirectedOffHost: return "The link answered with a login page, which the app can't fill in."
            case .notAPage: return "The link answered with something that isn't a Graded Takes page."
            }
        }
    }

    private let session: URLSession
    private let userAgent: String

    /// `timeout` is per request. Pages are under 1 MB; on a stadium
    /// connection 20 s is the difference between a fresh page and the
    /// saved copy with a banner, and the saved copy is the better answer.
    init(timeout: TimeInterval = 20) {
        let config = URLSessionConfiguration.ephemeral
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        config.timeoutIntervalForRequest = timeout
        config.timeoutIntervalForResource = timeout * 2
        config.waitsForConnectivity = false
        config.httpAdditionalHeaders = ["Accept": "text/html, application/json;q=0.9, */*;q=0.5"]
        session = URLSession(configuration: config)
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        userAgent = "GradedTakes/\(version) (iOS)"
    }

    /// Fetches `path` under `base`. `etag` is the value stored with the
    /// copy on disk; when the server still has that version it answers 304
    /// and the caller keeps the copy.
    func fetch(base: URL, path: String, etag: String?) async throws -> Outcome {
        guard let url = URL(string: path, relativeTo: base)?.absoluteURL else {
            throw Failure.notFound
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        if let etag, !etag.isEmpty {
            request.setValue(etag, forHTTPHeaderField: "If-None-Match")
        }

        let data: Data
        let response: URLResponse
        do {
            // The delegate refuses any redirect off the link's host BEFORE
            // it is followed: a login wall's redirect would otherwise be
            // fetched with the original URL - the token - in its query string.
            let redirects = SameHostRedirects(host: base.host ?? "")
            (data, response) = try await session.data(for: request, delegate: redirects)
        } catch let error as URLError {
            throw Failure(urlError: error)
        } catch {
            throw Failure.network
        }

        guard let http = response as? HTTPURLResponse else { throw Failure.network }

        // Belt and braces: whatever answered must be the link's host.
        if let finalHost = http.url?.host?.lowercased(),
           let expected = base.host?.lowercased(),
           finalHost != expected {
            throw Failure.redirectedOffHost
        }

        switch http.statusCode {
        case 200:
            if path.lowercased().hasSuffix(".html") {
                let mime = (http.mimeType ?? "").lowercased()
                guard mime.isEmpty || mime.contains("html") else { throw Failure.notAPage }
            }
            let tag = http.value(forHTTPHeaderField: "ETag")
            return .fresh(data, etag: tag)
        case 304:
            return .notModified
        case 301, 302, 303, 307, 308:
            // A redirect that reached us un-followed is one the delegate
            // refused, i.e. off the link's host: the login-wall case.
            throw Failure.redirectedOffHost
        case 404, 410:
            throw Failure.notFound
        default:
            throw Failure.status(http.statusCode)
        }
    }
}

/// Per-request URLSession task delegate: follows a redirect only when it
/// stays on the link's host (http -> https, a trailing slash); returns nil
/// for any other host so the session delivers the 3xx itself and the
/// original URL - which carries the token - never leaves that host.
private final class SameHostRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    private let host: String

    init(host: String) {
        self.host = host.lowercased()
    }

    // The completion-handler form, as the ObjC protocol declares it. (The
    // async form crashes the Swift 6.3 frontend while emitting its ObjC
    // thunk under NonisolatedNonsendingByDefault.)
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        guard let target = request.url?.host?.lowercased(), target == host else {
            completionHandler(nil)
            return
        }
        completionHandler(request)
    }
}

private extension PageFetcher.Failure {
    init(urlError: URLError) {
        switch urlError.code {
        case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed,
             .internationalRoamingOff, .cannotFindHost, .cannotConnectToHost:
            self = .offline
        case .timedOut:
            self = .timedOut
        default:
            self = .network
        }
    }
}
