//  WebView.swift
//  GradedTakes
//
//  UIViewRepresentable around WKWebView (shape B in the brief: works on
//  iOS 17+, battle-tested, first-class custom-scheme loading). The web view
//  shows exactly one thing - this reader's pages, served through
//  gradedtakes-pages:// - and refuses everything else:
//
//    gradedtakes-pages://...   allowed (the pages, served by PageSchemeHandler)
//    https://<link host>/<token>/...   rewritten to the scheme and loaded in-app
//    http(s) anything else     cancelled here, opened outside the web view
//                              (ESPN / Yahoo app via universal link, else
//                              SFSafariViewController) - see ExternalLinks
//    mailto:, tel:, sms:       cancelled here, handed to the system
//    anything else             cancelled
//
//  Referrer: the document URL never contains the token (PageScheme), the
//  renderer already emits <meta name="referrer" content="no-referrer">,
//  and a second copy of that meta is injected at document start for any
//  page that might lack it. Nothing that starts inside this web view can
//  carry the private link to another host.
//
//  App mode and theme: PageSchemeHandler stamps <html data-app="ios"
//  data-theme="light|dark"> on every page it serves, so the page knows it
//  is inside the shell and paints in the phone's theme from the first
//  frame. When the appearance changes while a page is up, the trait
//  change is forwarded into the live document (themeScript) so the page
//  follows the phone without a reload.
//
//  Swift 6: WKNavigationDelegate is a @MainActor protocol, so the
//  Coordinator is @MainActor and uses the async policy method (the
//  completion-handler form's handler became @MainActor in the iOS 18 SDK
//  and broke the old signature - Swift forums 78962).

import SwiftUI
import WebKit

/// A handle MainView keeps so native buttons can reach the live web view
/// (reload after pull-to-refresh, PDF for the share sheet).
@MainActor
final class WebViewProxy {
    weak var webView: WKWebView?

    func reload() {
        webView?.reload()
    }

    /// The current page as a PDF, for the share sheet. Renders what is on
    /// screen, so a saved copy shares as a saved copy.
    func pdf() async throws -> Data {
        guard let webView else { throw URLError(.cancelled) }
        return try await webView.pdf(configuration: WKPDFConfiguration())
    }
}

struct WebView: UIViewRepresentable {
    /// A command into the web view; a new id reloads even the same path.
    let request: NavigationRequest
    let pages: PageService
    let proxy: WebViewProxy
    /// The reader's link, to recognise absolute links back into their own pages.
    let link: PrivateLink?
    /// The web view committed a page at this path (relative to the link).
    let onNavigated: @MainActor (String) -> Void
    /// A link that must open outside the web view.
    let onExternal: @MainActor (URL) -> Void
    /// Navigation started / ended, for the thin gold progress line.
    let onLoadingChanged: @MainActor (Bool) -> Void
    /// The reader pulled to refresh (the reload itself happens here).
    let onRefresh: @MainActor () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self, schemeHandler: PageSchemeHandler(service: pages))
    }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(context.coordinator.schemeHandler, forURLScheme: PageScheme.scheme)
        // The document URL never contains the token, so the default
        // (persistent) store is safe and keeps the pages' localStorage
        // prefs (theme, density, quiet mode) across launches.
        config.websiteDataStore = .default()
        config.applicationNameForUserAgent = "GradedTakes"
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.userContentController.addUserScript(WKUserScript(
            source: Self.noReferrerScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: false
        ))
        config.userContentController.addUserScript(WKUserScript(
            source: Self.appModeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsLinkPreview = false           // a preview sheet would show scheme URLs and pre-load external links
        webView.isOpaque = false                    // no white flash over the paper ground
        webView.backgroundColor = Brand.uiGround
        webView.scrollView.backgroundColor = Brand.uiGround
        // Native chrome encloses the web view above and below, so it sits
        // entirely inside the safe area and must not inset itself again.
        webView.scrollView.contentInsetAdjustmentBehavior = .never

        let refresh = UIRefreshControl()
        refresh.tintColor = Brand.uiGold
        refresh.addTarget(context.coordinator, action: #selector(Coordinator.refreshPulled(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refresh

        // Appearance changed while a page is showing: retint the live
        // document. (The next page load is stamped by the scheme handler.)
        // UIKit calls trait-change handlers on the main thread; the
        // closure type is not annotated, hence assumeIsolated.
        webView.registerForTraitChanges([UITraitUserInterfaceStyle.self]) { (view: WKWebView, _: UITraitCollection) in
            MainActor.assumeIsolated {
                view.evaluateJavaScript(Self.themeScript(PageSchemeHandler.theme(of: view)), completionHandler: nil)
            }
        }

        context.coordinator.webView = webView
        proxy.webView = webView
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.parent = self
        if context.coordinator.lastRequestID != request.id {
            context.coordinator.lastRequestID = request.id
            webView.load(URLRequest(url: PageScheme.url(for: request.path)))
        }
    }

    /// Belt and braces for the referrer: the renderer emits this meta tag
    /// already; this adds it to any document that lacks one, before the
    /// document has a chance to request anything.
    static let noReferrerScript = """
    (function(){try{var d=document;if(d.querySelector('meta[name="referrer"]'))return;\
    var m=d.createElement('meta');m.setAttribute('name','referrer');m.setAttribute('content','no-referrer');\
    (d.head||d.documentElement).appendChild(m);}catch(e){}})();
    """

    /// Belt and braces for app mode: the scheme handler already stamps
    /// data-app="ios" into the served bytes (PageMarkup); this sets it at
    /// document start on any main-frame document that arrived without it,
    /// before the page's own scripts run (docs/APP_MODE.md: the shell's
    /// theme script steps aside when data-app is present).
    static let appModeScript = """
    (function(){try{var r=document.documentElement;\
    if(!r.hasAttribute('data-app'))r.setAttribute('data-app','\(PageMarkup.app)');}catch(e){}})();
    """

    /// Sets data-theme on the live document to the phone's appearance.
    /// `theme.rawValue` is "light" or "dark" - never reader input.
    static func themeScript(_ theme: PageMarkup.Theme) -> String {
        "(function(){try{document.documentElement.setAttribute('data-theme','\(theme.rawValue)');}catch(e){}})();"
    }

    // MARK: Coordinator

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var parent: WebView
        let schemeHandler: PageSchemeHandler
        var lastRequestID: UUID?
        weak var webView: WKWebView?

        init(parent: WebView, schemeHandler: PageSchemeHandler) {
            self.parent = parent
            self.schemeHandler = schemeHandler
        }

        @objc func refreshPulled(_ sender: UIRefreshControl) {
            parent.onRefresh()
            webView?.reload()
        }

        // MARK: Policy

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
            guard let url = navigationAction.request.url else { return .cancel }

            if PageScheme.isSchemeURL(url) {
                // target="_blank" inside our own pages: load it here instead.
                if navigationAction.targetFrame == nil {
                    webView.load(navigationAction.request)
                    return .cancel
                }
                return .allow
            }

            if url.scheme == "about" { return .allow }

            if url.scheme == "http" || url.scheme == "https" {
                // An absolute link back into the reader's own pages stays in-app.
                if let link = parent.link, let path = link.relativePath(of: url) {
                    webView.load(URLRequest(url: PageScheme.url(for: path)))
                    return .cancel
                }
                // fantasy.espn.com, football.fantasysports.yahoo.com, a source's
                // article: never inside this web view.
                parent.onExternal(url)
                return .cancel
            }

            if ["mailto", "tel", "sms"].contains(url.scheme?.lowercased() ?? "") {
                parent.onExternal(url)
                return .cancel
            }

            return .cancel
        }

        // MARK: Progress

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            parent.onLoadingChanged(true)
        }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            if let url = webView.url, let path = PageScheme.path(from: url) {
                // A back-swipe restored from WebKit's back/forward cache never
                // reaches the scheme handler, so `served` still describes the
                // page the reader LEFT and a saved copy could show with no
                // banner. Reload through the handler so the banner is derived
                // from this page. Only pages publish `served` (PageService
                // .serve), so only pages are compared - anything else would
                // reload forever.
                if path.lowercased().hasSuffix(".html"), path != parent.pages.served?.path {
                    webView.reload()
                }
                parent.onNavigated(path + (url.fragment.map { "#" + $0 } ?? ""))
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            finished(webView)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
            finished(webView)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error) {
            finished(webView)
        }

        private func finished(_ webView: WKWebView) {
            parent.onLoadingChanged(false)
            webView.scrollView.refreshControl?.endRefreshing()
            if let url = webView.url, let path = PageScheme.path(from: url) {
                parent.onNavigated(path + (url.fragment.map { "#" + $0 } ?? ""))
            }
        }

        // MARK: WKUIDelegate

        /// window.open / target=_blank. Never a second web view: our own
        /// pages load here, anything else goes outside.
        func webView(
            _ webView: WKWebView,
            createWebViewWith configuration: WKWebViewConfiguration,
            for navigationAction: WKNavigationAction,
            windowFeatures: WKWindowFeatures
        ) -> WKWebView? {
            if let url = navigationAction.request.url {
                if PageScheme.isSchemeURL(url) {
                    webView.load(navigationAction.request)
                } else if url.scheme == "http" || url.scheme == "https" {
                    if let link = parent.link, let path = link.relativePath(of: url) {
                        webView.load(URLRequest(url: PageScheme.url(for: path)))
                    } else {
                        parent.onExternal(url)
                    }
                }
            }
            return nil
        }
    }
}
