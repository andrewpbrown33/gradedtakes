//  AppDelegate.swift
//  GradedTakes
//
//  Only what a SwiftUI App cannot do on its own: the APNs registration
//  callbacks, the notification-center delegate, and the silent-push hook.
//  Installed once via @UIApplicationDelegateAdaptor in GradedTakesApp.
//
//  Concurrency (from the brief; verified against the iOS 17 SDK here):
//    - UIApplicationDelegate is a @MainActor protocol, so this class is
//      @MainActor and its UIApplication callbacks are isolated.
//    - UNUserNotificationCenterDelegate is NOT actor-isolated and its
//      parameters are not Sendable. Its methods are `nonisolated`; each
//      one pulls the Sendable facts it needs (a String, a dictionary of
//      plain values) out of the notification first, then hops to the main
//      actor. Marking them @MainActor is a compile error in Swift 6.
//    - Nothing in this file logs. The private link is never in scope.

import UIKit
import UserNotifications

@MainActor
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // "Always assign an object to the delegate property before performing
        // any tasks that might interact with that delegate" - so here, first.
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    // MARK: APNs registration

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        let model = AppModel.shared
        model.push.deviceTokenReceived(hex, link: model.links.link)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: any Error) {
        AppModel.shared.push.registrationFailed()
    }

    // MARK: Silent push (UIBackgroundModes = remote-notification)

    /// {"aps":{"content-available":1},"path":"lineup-espn-1-week1.html"}:
    /// warm the page and the widget before the visible alert lands. The
    /// system allows about 30 seconds; a page is under 1 MB.
    func application(
        _ application: UIApplication,
        didReceiveRemoteNotification userInfo: [AnyHashable: Any]
    ) async -> UIBackgroundFetchResult {
        let model = AppModel.shared
        guard model.links.link != nil else { return .noData }
        if let needs = Self.needsJSON(in: userInfo) {
            model.pages.applyNeeds(json: needs)
        }
        let path = (userInfo["path"] as? String).flatMap(Router.sanitize) ?? PageScheme.homePath
        // prefetch, not serve: serve publishes the banner state for the page
        // on screen, and this push may name a different page.
        await model.pages.prefetch(path: path)
        await model.pages.refreshNeeds(force: true)
        return .newData
    }

    // MARK: UNUserNotificationCenterDelegate (nonisolated - see header)

    /// The app is in the foreground when the alert arrives: still show it.
    /// A ruled-out starter is worth a banner even mid-scroll.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        let needs = Self.needsJSON(in: notification.request.content.userInfo)
        if let needs {
            await MainActor.run { AppModel.shared.pages.applyNeeds(json: needs) }
        }
        return [.banner, .list, .sound, .badge]
    }

    /// The reader tapped the notification: open the page it names.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let userInfo = response.notification.request.content.userInfo
        let path = userInfo["path"] as? String
        let needs = Self.needsJSON(in: userInfo)
        await MainActor.run {
            let model = AppModel.shared
            if let needs { model.pages.applyNeeds(json: needs) }
            model.router.go(to: path ?? PageScheme.homePath)
        }
    }

    /// The payload's "needs" object as JSON bytes. Data is Sendable, so it
    /// can cross from a nonisolated delegate method to the main actor; the
    /// dictionary itself cannot. Anything that is not valid JSON is dropped.
    nonisolated private static func needsJSON(in userInfo: [AnyHashable: Any]) -> Data? {
        guard let needs = userInfo["needs"] as? [String: Any],
              JSONSerialization.isValidJSONObject(needs)
        else { return nil }
        return try? JSONSerialization.data(withJSONObject: needs)
    }
}
