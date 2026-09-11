//  LinkStore.swift
//  GradedTakes
//
//  The app's view of the private link: present or not, and the two
//  operations Settings offers (replace, forget). Backed by KeychainStore.
//  This is the only type that ever holds the PrivateLink in memory for the
//  UI; nothing observes the token itself, only `link` as a whole.

import Foundation
import Observation

@MainActor @Observable
final class LinkStore {
    /// Keychain account under KeychainStore.service.
    static let account = "private-link"

    /// The link, or nil on first launch / after "Forget this link".
    private(set) var link: PrivateLink?

    /// Set when the Keychain refused to answer (very rare: the phone has
    /// not been unlocked since boot, or a corrupt item). The onboarding
    /// screen shows a calm sentence instead of asking for the link again.
    private(set) var lastFailure: KeychainStore.Failure?

    init() {
        reload()
    }

    /// Re-reads the Keychain. Called at init and after the phone unlocks.
    func reload() {
        do {
            if let stored = try KeychainStore.read(account: Self.account),
               case .success(let parsed) = PrivateLink.parse(stored) {
                link = parsed
            } else {
                link = nil
            }
            lastFailure = nil
        } catch let failure as KeychainStore.Failure {
            lastFailure = failure
        } catch {
            lastFailure = nil
        }
    }

    /// Stores a new link. The caller is responsible for wiping caches when
    /// the link changed (AppModel.replaceLink does that).
    func save(_ newLink: PrivateLink) throws {
        try KeychainStore.write(newLink.canonical, account: Self.account)
        link = newLink
        lastFailure = nil
    }

    /// Removes the link from the Keychain.
    func forget() throws {
        try KeychainStore.delete(account: Self.account)
        link = nil
        lastFailure = nil
    }
}
