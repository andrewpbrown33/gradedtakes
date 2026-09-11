//  GradedTakesWidgetBundle.swift
//  GradedTakesWidget
//
//  The extension's entry point. One widget today; a Live Activity for the
//  Sunday matchup would be added here later (docs/APPSTORE.md, Tier 3).
//  The Info.plist NSExtensionPointIdentifier is com.apple.widgetkit-extension
//  (generated from project.yml).

import SwiftUI
import WidgetKit

@main
struct GradedTakesWidgetBundle: WidgetBundle {
    var body: some Widget {
        NeedsWidget()
    }
}
