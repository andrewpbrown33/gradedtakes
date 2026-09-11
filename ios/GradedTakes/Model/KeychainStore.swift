//  KeychainStore.swift
//  GradedTakes
//
//  One secret string in the iPhone Keychain, Security framework only.
//  Pattern from Apple's samples ("Adding a password to the keychain",
//  "Searching for keychain items"): a generic-password item keyed by
//  service + account.
//
//  Accessibility is kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly:
//  readable once the phone has been unlocked since boot (the app only
//  reads it in the foreground), never migrated to another device by a
//  backup or a transfer. The private link is a per-phone secret; if the
//  reader gets a new phone they paste it again.
//
//  Nothing here logs. A failure surfaces as a status code, not as the value.

import Foundation
import Security

enum KeychainStore {
    /// Namespaces this app's items. Never changes once shipped, or every
    /// reader loses their link on update.
    static let service = "com.gradedtakes.app"

    struct Failure: Error, Equatable {
        let status: OSStatus
        var message: String {
            (SecCopyErrorMessageString(status, nil) as String?) ?? "Keychain error \(status)"
        }
    }

    /// The stored string for `account`, or nil when there is none.
    static func read(account: String) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecReturnData as String: true,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:
            guard let data = item as? Data else { return nil }
            return String(data: data, encoding: .utf8)
        case errSecItemNotFound:
            return nil
        default:
            throw Failure(status: status)
        }
    }

    /// Creates or replaces the item.
    static func write(_ value: String, account: String) throws {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var add = query
            add.merge(attributes) { _, new in new }
            status = SecItemAdd(add as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw Failure(status: status) }
    }

    /// Removes the item. Not finding it is not an error.
    static func delete(account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw Failure(status: status)
        }
    }
}
