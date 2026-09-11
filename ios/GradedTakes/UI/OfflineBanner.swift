//  OfflineBanner.swift
//  GradedTakes
//
//  The honesty banner. Shown whenever the page on screen is not the copy
//  the server confirmed this session; never absent when a saved copy is
//  showing. The date is the moment that copy was fetched, from the cache
//  manifest - not a guess and not a file timestamp.
//
//  Copy, by state (install.html sets the tone: name the week and the
//  moment, say nothing has been re-checked):
//    offline, saved copy    "Offline - showing week 1 as of Sun 14 Sep, 09:12"
//    online, fetch failed   "Couldn't refresh - showing week 1 as of ..."
//    offline, nothing saved "Offline - nothing saved for this page yet"
//    online, nothing saved  "Couldn't fetch this page" + the reason

import SwiftUI

struct BannerState: Equatable {
    let title: String
    let detail: String?
}

extension BannerState {
    /// Derives the banner from what was served and whether there is a path.
    static func make(served: PageService.ServedPage?, isOnline: Bool, failure: PageFetcher.Failure?) -> BannerState? {
        guard let served else { return nil }
        let week = served.week.map { "week \($0)" } ?? "the saved copy"
        switch served.source {
        case .live:
            return nil
        case .saved(let date):
            let stamp = date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute())
            let offline = !isOnline || failure == .offline
            return BannerState(
                title: offline ? "Offline \u{2014} showing \(week) as of \(stamp)" : "Couldn't refresh \u{2014} showing \(week) as of \(stamp)",
                detail: offline ? "Nothing in it has been re-checked since then." : failure?.message
            )
        case .missing:
            let offline = !isOnline || failure == .offline
            return BannerState(
                title: offline ? "Offline \u{2014} nothing saved for this page yet" : "Couldn't fetch this page",
                detail: offline ? "Open it once while you have a signal and it stays on your phone." : failure?.message
            )
        }
    }
}

struct OfflineBanner: View {
    let state: BannerState
    let retry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Rectangle()
                .fill(Brand.gold)
                .frame(width: 3)
                .clipShape(Capsule())
            VStack(alignment: .leading, spacing: 2) {
                Text(state.title)
                    .font(.subheadline.weight(.semibold))
                if let detail = state.detail {
                    Text(detail)
                        .font(.caption)
                        .opacity(0.8)
                }
            }
            .foregroundStyle(Brand.navy)
            Spacer(minLength: 8)
            Button("Retry", action: retry)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Brand.navy)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Brand.gold, in: Capsule())
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Brand.washHot)
        .accessibilityElement(children: .combine)
    }
}
