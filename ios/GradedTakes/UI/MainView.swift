//  MainView.swift
//  GradedTakes
//
//  The shell: a navy top bar (wordmark, week, league, share, settings),
//  the honesty banner when it applies, the web view, and a navy bottom
//  bar with the product's five destinations. One web view for all five;
//  the bar highlights whatever the web view is actually showing, so
//  in-page links and the back gesture keep it truthful.
//
//  Native value the reviewer can see in ninety seconds (docs/APPSTORE.md,
//  guideline 4.2): native navigation, pull-to-refresh, the share sheet,
//  haptics on a destination change, offline with a dated banner, and the
//  push prompt at the right moment (after the first page, not before).

import SwiftUI
import UIKit

struct MainView: View {
    @Environment(AppModel.self) private var model
    @Environment(Router.self) private var router
    @Environment(PageService.self) private var pages
    @Environment(Connectivity.self) private var connectivity
    @Environment(LinkStore.self) private var links
    @Environment(PushRegistrar.self) private var push

    @State private var proxy = WebViewProxy()
    @State private var showSettings = false
    @State private var showShareOptions = false
    @State private var confirmLinkShare = false
    @State private var shareItem: ShareItem?
    @State private var isMakingPDF = false
    @State private var askedForPushThisSession = false

    var body: some View {
        @Bindable var router = router
        VStack(spacing: 0) {
            topBar
            if let banner = BannerState.make(served: pages.served, isOnline: connectivity.isOnline, failure: pages.lastFailure) {
                OfflineBanner(state: banner) { proxy.reload() }
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
            WebView(
                request: router.request,
                pages: pages,
                proxy: proxy,
                link: links.link,
                onNavigated: { path in router.didShow(path: path) },
                onExternal: { url in
                    ExternalLinks.open(url) { safariURL in
                        router.safariLink = ExternalLink(url: safariURL)
                    }
                },
                onLoadingChanged: { loading in pages.isLoading = loading },
                onRefresh: {
                    Task {
                        await pages.refreshSiteMap(force: true)
                        await pages.refreshNeeds(force: true)
                    }
                }
            )
            .background(Brand.ground)
            // A new link is a new person: tear the web view down so nothing
            // of the previous pages survives in WebKit's back/forward cache.
            .id(links.link?.fingerprint ?? "")
            bottomBar
        }
        .background(Brand.navy.ignoresSafeArea())
        .animation(.easeInOut(duration: 0.2), value: pages.served)
        .fullScreenCover(item: $router.safariLink) { external in
            SafariView(url: external.url)
                .ignoresSafeArea()
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .sheet(item: $shareItem) { item in
            ShareSheet(items: item.items)
                .presentationDetents([.medium, .large])
        }
        .confirmationDialog("Share", isPresented: $showShareOptions, titleVisibility: .hidden) {
            Button("Share this page as a PDF") { sharePDF() }
            Button("Share my private link\u{2026}") { confirmLinkShare = true }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("This link is the key to your pages.", isPresented: $confirmLinkShare, titleVisibility: .visible) {
            Button("Share the link") { shareLink() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Anyone who has it can read your lineups and your trade desk. Share it with yourself \u{2014} another device, a note \u{2014} or with someone you'd hand your phone to.")
        }
        .onChange(of: pages.served) { _, served in
            maybeAskForPush(after: served)
        }
    }

    // MARK: Top bar

    private var topBar: some View {
        HStack(spacing: 10) {
            DiamondMark(size: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text(Brand.wordmark)
                    .font(.system(size: 13, weight: .semibold))
                    .tracking(2.2)
                    .foregroundStyle(Brand.navText)
                Text(statusLine)
                    .font(.system(size: 11))
                    .foregroundStyle(Brand.navText.opacity(0.72))
                    .lineLimit(1)
            }
            Spacer(minLength: 6)

            if pages.isLoading {
                ProgressView()
                    .tint(Brand.gold)
                    .controlSize(.small)
                    .accessibilityLabel("Loading")
            } else if let week = pages.served?.week ?? pages.siteMap.week {
                Text("WK \(week)")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Brand.navy)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Brand.gold, in: RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .accessibilityLabel("Week \(week)")
            }

            if pages.siteMap.leagues.count > 1 {
                leagueMenu
            }

            Button(action: { showShareOptions = true }) {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 17, weight: .medium))
                    .frame(width: 36, height: 36)
            }
            .foregroundStyle(Brand.navText)
            .disabled(isMakingPDF)
            .accessibilityLabel("Share")

            Button(action: { showSettings = true }) {
                Image(systemName: "gearshape")
                    .font(.system(size: 17, weight: .medium))
                    .frame(width: 36, height: 36)
            }
            .foregroundStyle(Brand.navText)
            .accessibilityLabel("Settings")
        }
        .padding(.leading, 16)
        .padding(.trailing, 6)
        .padding(.vertical, 6)
        .background(Brand.navy)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Brand.navLine).frame(height: 1)
        }
    }

    /// One short line under the wordmark that always says what is on screen.
    private var statusLine: String {
        guard let served = pages.served else { return pages.isLoading ? "Fetching your pages\u{2026}" : "Your pages" }
        switch served.source {
        case .live(let date):
            return "Live \u{00B7} checked \(date.formatted(date: .omitted, time: .shortened))"
        case .saved(let date):
            return "Saved copy \u{00B7} \(date.formatted(.dateTime.weekday(.abbreviated).hour().minute()))"
        case .missing:
            return "Nothing saved for this page"
        }
    }

    private var leagueMenu: some View {
        let selection = Binding<String>(
            get: { router.selectedLeague ?? pages.siteMap.leagues.first ?? "" },
            set: { league in router.selectLeague(league, in: pages.siteMap) }
        )
        return Menu {
            Picker("League", selection: selection) {
                ForEach(pages.siteMap.leagues, id: \.self) { league in
                    Text(league).tag(league)
                }
            }
        } label: {
            HStack(spacing: 3) {
                Text(router.selectedLeague ?? pages.siteMap.leagues.first ?? "")
                    .font(.system(size: 11, weight: .semibold))
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .bold))
            }
            .foregroundStyle(Brand.navText)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Brand.navRaised, in: Capsule())
        }
        .accessibilityLabel("League")
    }

    // MARK: Bottom bar

    private var bottomBar: some View {
        HStack(spacing: 0) {
            ForEach(Destination.allCases) { destination in
                let selected = router.currentDestination == destination
                Button {
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    router.go(to: destination, in: pages.siteMap)
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: destination.symbol)
                            .font(.system(size: 19, weight: selected ? .semibold : .regular))
                        Text(destination.title)
                            .font(.system(size: 10, weight: selected ? .semibold : .regular))
                            .lineLimit(1)
                            .minimumScaleFactor(0.85)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)
                    .padding(.bottom, 2)
                    .foregroundStyle(selected ? Brand.gold : Brand.navText.opacity(0.78))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(destination.title)
                .accessibilityAddTraits(selected ? [.isSelected] : [])
            }
        }
        .background(Brand.navy)
        .overlay(alignment: .top) {
            Rectangle().fill(Brand.navLine).frame(height: 1)
        }
    }

    // MARK: Share

    private func sharePDF() {
        guard !isMakingPDF else { return }
        isMakingPDF = true
        Task {
            defer { isMakingPDF = false }
            do {
                let data = try await proxy.pdf()
                let week = pages.served?.week.map { "week\($0)-" } ?? ""
                let page = router.currentDestination?.title.replacingOccurrences(of: " ", with: "") ?? "Page"
                let url = FileManager.default.temporaryDirectory
                    .appendingPathComponent("GradedTakes-\(week)\(page).pdf", isDirectory: false)
                try data.write(to: url, options: .atomic)
                shareItem = ShareItem(items: [url])
            } catch {
                // The page is still loading or the web view is gone; nothing to share yet.
            }
        }
    }

    private func shareLink() {
        guard let link = links.link else { return }
        let file = router.currentPath.split(separator: "#").first.map(String.init) ?? PageScheme.homePath
        guard let url = link.url(forPath: file) else { return }
        shareItem = ShareItem(items: [url])
    }

    // MARK: Push prompt

    /// Ask for notifications once, and only after the reader has seen a
    /// real page - the moment the value is obvious.
    private func maybeAskForPush(after served: PageService.ServedPage?) {
        guard let served, case .live = served.source,
              !push.hasAsked, !askedForPushThisSession
        else { return }
        askedForPushThisSession = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            await push.requestAuthorization()
        }
    }
}
