//  NeedsWidget.swift
//  GradedTakesWidget
//
//  "2 calls need you" on the home screen (small, medium) and the lock
//  screen (accessory rectangular). Reads needs.json from the App Group
//  container (NeedsStore, ios/Shared) and nothing else: no network, no
//  Keychain, no private link. Tapping opens the app at the page the
//  state names (gradedtakes://needs, handled by Router).
//
//  Honesty: when the state is older than six hours the widget prints
//  "as of <how long ago>" under the count (a relative date, so a two-day-old
//  count never reads as today's), so a Sunday-morning count is never
//  mistaken for a Sunday-afternoon one. No state at all -> "Open the app".
//
//  Design: navy ground in every mode (containerBackground), the gold
//  diamond mark, the count large, the headline small. One accent.
//
//  Swift 6: TimelineProvider is not actor-isolated; this provider has no
//  state and only reads a file, so it needs no isolation of its own.
//  Timelines refresh every 30 minutes only to re-evaluate staleness; the
//  app reloads the timeline itself after every write, and reloads while
//  the app is in the foreground do not count against the daily budget.

import SwiftUI
import WidgetKit

struct NeedsEntry: TimelineEntry {
    let date: Date
    let state: NeedsState?
}

struct NeedsProvider: TimelineProvider {
    func placeholder(in context: Context) -> NeedsEntry {
        NeedsEntry(date: .now, state: NeedsState(count: 2, headline: "2 calls need you", week: 1, updated: nil, path: nil, fetchedAt: .now))
    }

    func getSnapshot(in context: Context, completion: @escaping (NeedsEntry) -> Void) {
        if context.isPreview {
            completion(placeholder(in: context))
        } else {
            completion(NeedsEntry(date: .now, state: NeedsStore.read()))
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NeedsEntry>) -> Void) {
        let entry = NeedsEntry(date: .now, state: NeedsStore.read())
        let next = Date.now.addingTimeInterval(30 * 60)
        completion(Timeline(entries: [entry], policy: .after(next)))
    }
}

struct NeedsWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: NeedsEntry

    var body: some View {
        Group {
            switch family {
            case .accessoryRectangular:
                lockScreen
            case .systemMedium:
                medium
            default:
                small
            }
        }
        .widgetURL(NeedsStore.widgetDeepLink)
        .containerBackground(for: .widget) { Brand.navy }
    }

    // MARK: Faces

    private var small: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                DiamondMark(size: 12)
                Text(Brand.wordmark)
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(1.6)
                    .foregroundStyle(Brand.navText.opacity(0.8))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            Spacer(minLength: 4)
            if let state = entry.state {
                Text("\(state.count)")
                    .font(.system(size: 44, weight: .bold, design: .rounded))
                    .foregroundStyle(state.count > 0 ? Brand.gold : Brand.navText)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(state.headline)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Brand.navText)
                    .lineLimit(2)
                    .minimumScaleFactor(0.85)
                asOf(state)
            } else {
                Text("Open the app")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Brand.navText)
                Text("Your week is waiting.")
                    .font(.system(size: 11))
                    .foregroundStyle(Brand.navText.opacity(0.72))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var medium: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                DiamondMark(size: 22)
                Spacer(minLength: 2)
                if let state = entry.state {
                    Text("\(state.count)")
                        .font(.system(size: 52, weight: .bold, design: .rounded))
                        .foregroundStyle(state.count > 0 ? Brand.gold : Brand.navText)
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                } else {
                    Text("\u{2014}")
                        .font(.system(size: 52, weight: .bold, design: .rounded))
                        .foregroundStyle(Brand.navText.opacity(0.5))
                }
            }
            .frame(width: 84, alignment: .leading)

            VStack(alignment: .leading, spacing: 4) {
                Text(Brand.wordmark)
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(1.6)
                    .foregroundStyle(Brand.navText.opacity(0.8))
                if let state = entry.state {
                    Text(state.headline)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Brand.navText)
                        .lineLimit(2)
                    if let week = state.week {
                        Text("Week \(week)")
                            .font(.system(size: 12))
                            .foregroundStyle(Brand.navText.opacity(0.72))
                    }
                    asOf(state)
                } else {
                    Text("Open the app")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Brand.navText)
                    Text("Your week is waiting.")
                        .font(.system(size: 12))
                        .foregroundStyle(Brand.navText.opacity(0.72))
                }
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var lockScreen: some View {
        HStack(spacing: 8) {
            DiamondMark(size: 14)
                .widgetAccentable()
            VStack(alignment: .leading, spacing: 1) {
                if let state = entry.state {
                    Text(state.headline)
                        .font(.headline)
                        .lineLimit(1)
                    if state.isStale {
                        Text("as of \(state.fetchedAt, style: .relative)")
                            .font(.caption2)
                    } else if let week = state.week {
                        Text("Week \(week)")
                            .font(.caption2)
                    }
                } else {
                    Text("Graded Takes")
                        .font(.headline)
                    Text("Open the app")
                        .font(.caption2)
                }
            }
            Spacer(minLength: 0)
        }
    }

    /// The honest line: only when the state is old.
    @ViewBuilder
    private func asOf(_ state: NeedsState) -> some View {
        if state.isStale {
            Text("as of \(state.fetchedAt, style: .relative)")
                .font(.system(size: 10))
                .foregroundStyle(Brand.navText.opacity(0.65))
        }
    }
}

struct NeedsWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: NeedsStore.widgetKind, provider: NeedsProvider()) { entry in
            NeedsWidgetView(entry: entry)
        }
        .configurationDisplayName("Needs you")
        .description("How many calls need you before kickoff.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}
