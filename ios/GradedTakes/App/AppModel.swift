//  AppModel.swift
//  GradedTakes
//
//  The object graph, built once. SwiftUI reads it from the environment;
//  AppDelegate (which SwiftUI constructs, not us) reaches it through
//  `shared`. Everything in here is main-actor state except OfflineStore,
//  which is its own actor so file IO never blocks a frame.

import Foundation
import Observation
import UserNotifications

@MainActor @Observable
final class AppModel {
    static let shared = AppModel()

    let links = LinkStore()
    let connectivity = Connectivity()
    let store = OfflineStore()
    let router = Router()
    let push = PushRegistrar()
    let pages: PageService

    private init() {
        pages = PageService(links: links, connectivity: connectivity, store: store)
    }

    /// Onboarding and Settings > Replace. A different link means a different
    /// person's pages: the cache and the widget state are wiped first.
    func replaceLink(with newLink: PrivateLink) async throws {
        let changed = links.link != newLink
        if changed {
            await pages.clearCache()
        }
        try links.save(newLink)
        router.selectedLeague = nil
        router.go(to: PageScheme.homePath)
        push.linkDidChange(newLink)
    }

    /// Settings > Forget. Back to the paste screen with nothing left behind.
    func forgetLink() async throws {
        await pages.clearCache()
        try links.forget()
        router.selectedLeague = nil
        router.go(to: PageScheme.homePath)
    }

    /// Scene became active: re-check Keychain (first unlock), refresh the
    /// widget, keep the APNs token current, clear the badge.
    func becameActive() async {
        if links.link == nil { links.reload() }
        await push.registerIfAuthorized()
        await pages.refreshNeeds()
        try? await UNUserNotificationCenter.current().setBadgeCount(0)
    }
}
