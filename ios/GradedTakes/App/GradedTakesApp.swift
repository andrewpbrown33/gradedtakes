//  GradedTakesApp.swift
//  GradedTakes
//
//  The entry point. A SwiftUI App is scene-based already, which is what
//  Apple requires of apps built with the SDK after iOS 26 (WWDC25 282);
//  there is deliberately no UIWindow-in-AppDelegate path. The delegate
//  adaptor exists only for push callbacks.
//
//  Minimum iOS: 17.0 (project.yml). Chosen because Xcode 27 debugs iOS 17+,
//  @Observable / .onChange(of:) with two values / containerBackground need
//  17, and nothing here needs 18 or 26 - the league is not forced to update.

import SwiftUI

@main
struct GradedTakesApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var scenePhase

    /// The object graph. Built once; the delegate reaches the same instance
    /// through AppModel.shared.
    @State private var model = AppModel.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(model.links)
                .environment(model.router)
                .environment(model.pages)
                .environment(model.push)
                .environment(model.connectivity)
                .onOpenURL { url in
                    // Widget taps (gradedtakes://needs) and any gradedtakes:// link.
                    model.router.handle(url, needs: model.pages.needs)
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await model.becameActive() }
                    }
                }
        }
    }
}
