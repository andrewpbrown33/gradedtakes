//  OfflineStore.swift
//  GradedTakes
//
//  The last successfully fetched copy of every page, on disk, keyed by its
//  path under the private link ("home.html", "lineup-espn-1-week1.html",
//  "icons/icon.svg"). Because the pages are self-contained (fonts and
//  avatars are data: URIs, zero network at open) one file per page IS the
//  whole cache; there are no sub-resources to chase.
//
//  Why not WKWebView's own HTTP cache: it lives inside WKWebsiteDataStore
//  and exposes no API to pin or serve content offline. Why not URLCache:
//  it only governs our URLSession and would still leave "which copy is
//  this and when was it fetched" unanswerable. A manual store answers
//  that exactly, and the answer is what the offline banner prints.
//
//  Location: Application Support/Pages/, excluded from backup (it is a
//  cache, and it names the reader's leagues). The manifest carries the
//  fetch date INSIDE the JSON so the banner never has to read a file's
//  modification date (a "required reason" API).
//
//  The private link is not stored here in any form. Paths are relative.

import Foundation

actor OfflineStore {
    struct Entry: Sendable {
        let data: Data
        let fetchedAt: Date
        let etag: String?
    }

    struct Record: Codable, Sendable, Equatable {
        var fetchedAt: Date
        var etag: String?
        var bytes: Int
    }

    struct Manifest: Codable, Sendable, Equatable {
        var schema = "gradedtakes.cache/1"
        /// Path -> record. Paths are relative to the link, never absolute.
        var pages: [String: Record] = [:]
    }

    struct Summary: Sendable, Equatable {
        let pageCount: Int
        let bytes: Int
        let newest: Date?
        let oldest: Date?
    }

    private let directory: URL
    private let manifestURL: URL
    private var manifest: Manifest

    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = support.appendingPathComponent("Pages", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutableDir = dir
        try? mutableDir.setResourceValues(values)

        directory = dir
        manifestURL = dir.appendingPathComponent("manifest.json", isDirectory: false)
        if let data = try? Data(contentsOf: manifestURL),
           let loaded = try? OfflineStore.decoder().decode(Manifest.self, from: data) {
            manifest = loaded
        } else {
            manifest = Manifest()
        }
    }

    // MARK: Reading

    func record(for path: String) -> Record? {
        manifest.pages[path]
    }

    func read(_ path: String) -> Entry? {
        guard let record = manifest.pages[path],
              let data = try? Data(contentsOf: fileURL(for: path))
        else { return nil }
        return Entry(data: data, fetchedAt: record.fetchedAt, etag: record.etag)
    }

    func summary() -> Summary {
        let records = manifest.pages.values
        return Summary(
            pageCount: records.count,
            bytes: records.reduce(0) { $0 + $1.bytes },
            newest: records.map(\.fetchedAt).max(),
            oldest: records.map(\.fetchedAt).min()
        )
    }

    // MARK: Writing

    /// Stores a fresh copy. Atomic write, then the manifest.
    func write(_ path: String, data: Data, etag: String?, fetchedAt: Date) throws {
        try data.write(to: fileURL(for: path), options: .atomic)
        manifest.pages[path] = Record(fetchedAt: fetchedAt, etag: etag, bytes: data.count)
        try saveManifest()
    }

    /// The server said 304 Not Modified: the copy on disk is current as of now.
    func markVerified(_ path: String, at date: Date) {
        guard var record = manifest.pages[path] else { return }
        record.fetchedAt = date
        manifest.pages[path] = record
        try? saveManifest()
    }

    /// Everything gone. Used when the link is replaced or forgotten - the
    /// next reader must never see the previous reader's pages.
    func clear() throws {
        for path in manifest.pages.keys {
            try? FileManager.default.removeItem(at: fileURL(for: path))
        }
        manifest = Manifest()
        try saveManifest()
    }

    // MARK: Files

    /// "icons/icon.svg" -> "icons__icon.svg". Paths were validated by
    /// PageScheme.path(from:) before they reach here, so "/" is the only
    /// character that needs flattening.
    private func fileURL(for path: String) -> URL {
        let name = path.replacingOccurrences(of: "/", with: "__")
        return directory.appendingPathComponent(name, isDirectory: false)
    }

    private func saveManifest() throws {
        let data = try OfflineStore.encoder().encode(manifest)
        try data.write(to: manifestURL, options: .atomic)
    }

    private static func encoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.sortedKeys, .prettyPrinted]
        return e
    }

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }
}
