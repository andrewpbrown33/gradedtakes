//  SettingsView.swift
//  GradedTakes
//
//  Everything the reader can change, and everything the app should be
//  honest about: the link (masked; replace; forget), notifications (status,
//  Time Sensitive, registration), the saved copies (how many, how old,
//  clear), and what the app does not do (no analytics, no third-party code).
//
//  No red anywhere: "Forget" and "Clear" are plain buttons behind a
//  confirmation, not destructive-role buttons (which iOS paints red).

import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(LinkStore.self) private var links
    @Environment(PushRegistrar.self) private var push
    @Environment(PageService.self) private var pages
    @Environment(\.dismiss) private var dismiss

    @State private var showReplace = false
    @State private var confirmForget = false
    @State private var confirmClear = false
    @State private var cache: OfflineStore.Summary?
    @State private var registrationURLText = ""
    @State private var problem: String?

    var body: some View {
        NavigationStack {
            List {
                linkSection
                notificationsSection
                savedCopiesSection
                aboutSection
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(Brand.ground)
            .tint(Brand.goldInk)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task {
            registrationURLText = push.registrationURLString
            await push.refreshSettings()
            cache = await pages.cacheSummary()
        }
        .sheet(isPresented: $showReplace) {
            OnboardingView(isReplacing: true)
        }
        .confirmationDialog("Forget this link?", isPresented: $confirmForget, titleVisibility: .visible) {
            Button("Forget the link") { forget() }
            Button("Keep it", role: .cancel) {}
        } message: {
            Text("The link leaves the Keychain and every saved page is deleted from this phone. You will need the link again to come back.")
        }
        .confirmationDialog("Clear saved copies?", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Clear them") { clearCache() }
            Button("Keep them", role: .cancel) {}
        } message: {
            Text("With no signal there will be nothing to show until a page is opened again.")
        }
    }

    // MARK: Sections

    private var linkSection: some View {
        Section {
            if let link = links.link {
                LabeledContent("Address") {
                    Text(link.masked)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(Brand.muted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Button("Replace the link\u{2026}") { showReplace = true }
            Button("Forget this link") { confirmForget = true }
        } header: {
            Text("Your private link")
        } footer: {
            Text("Only the end of the address is shown. The whole link is in your iPhone's Keychain and nowhere else.")
        }
    }

    private var notificationsSection: some View {
        Section {
            LabeledContent("Notifications", value: authorizationText)
            LabeledContent("Time Sensitive", value: timeSensitiveText)
            if push.authorization == .notDetermined {
                Button("Turn on notifications") {
                    Task { await push.requestAuthorization() }
                }
            } else {
                Button("Open iOS Settings") { push.openSystemSettings() }
            }
            LabeledContent("Registered") {
                if push.isRegistering {
                    ProgressView().controlSize(.small)
                } else if let date = push.lastRegisteredAt {
                    Text(date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))
                        .foregroundStyle(Brand.muted)
                } else {
                    Text("Not yet").foregroundStyle(Brand.muted)
                }
            }
            if let failure = push.lastRegistrationFailure {
                Text(failure)
                    .font(.footnote)
                    .foregroundStyle(Brand.goldInk)
            }
            LabeledContent("Device token") {
                Text(push.deviceTokenHex ?? "Not yet")
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
            }
        } header: {
            Text("Notifications")
        } footer: {
            Text("The alert that matters is \u{201C}your starter was just ruled out\u{201D}, sent as Time Sensitive so it comes through a Focus mode. iOS lets you switch Time Sensitive off for this app in Settings. Your phone's notification token is sent to the Graded Takes server with a fingerprint of your link, never the link itself.")
        }
    }

    private var savedCopiesSection: some View {
        Section {
            if let cache, cache.pageCount > 0 {
                LabeledContent("Saved", value: "\(cache.pageCount) \(cache.pageCount == 1 ? "page" : "pages") \u{00B7} \(ByteCountFormatStyle().format(Int64(cache.bytes)))")
                if let newest = cache.newest {
                    LabeledContent("Newest", value: newest.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))
                }
                if let oldest = cache.oldest, cache.pageCount > 1 {
                    LabeledContent("Oldest", value: oldest.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))
                }
                Button("Clear saved copies") { confirmClear = true }
            } else {
                Text("Nothing saved yet. Every page you open while you have a signal is kept for when you don't.")
                    .foregroundStyle(Brand.muted)
            }
            if let needs = pages.needs {
                LabeledContent("Widget") {
                    Text("\(needs.headline) \u{00B7} \(needs.fetchedAt.formatted(date: .omitted, time: .shortened))")
                        .foregroundStyle(Brand.muted)
                        .lineLimit(1)
                }
            } else {
                LabeledContent("Widget", value: "Nothing published yet")
            }
        } header: {
            Text("Saved copies")
        } footer: {
            Text("With no signal the app shows the last copy of each page it fetched, with a banner naming the week and the moment it was fetched. It never shows a saved page as if it were live.")
        }
    }

    private var aboutSection: some View {
        Section {
            LabeledContent("Version", value: Self.versionText)
            LabeledContent("Alerts go to") {
                TextField("https://\u{2026}/api/push/register", text: $registrationURLText)
                    .font(.system(.footnote, design: .monospaced))
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .multilineTextAlignment(.trailing)
                    .onSubmit(saveRegistrationURL)
                    .onChange(of: registrationURLText) { _, _ in problem = nil }
            }
            if let problem {
                Text(problem).font(.footnote).foregroundStyle(Brand.goldInk)
            }
        } header: {
            Text("About")
        } footer: {
            Text("No analytics. No advertising. No third-party code. The app fetches your own pages from your private link and nothing else; the address above is where it registers for alerts. Change it only if you were told to.")
        }
    }

    // MARK: Text

    private var authorizationText: String {
        switch push.authorization {
        case .authorized: return "On"
        case .provisional: return "Quietly on"
        case .ephemeral: return "On for now"
        case .denied: return "Off"
        case .notDetermined: return "Not asked yet"
        @unknown default: return "Unknown"
        }
    }

    private var timeSensitiveText: String {
        switch push.timeSensitive {
        case .enabled: return "On"
        case .disabled: return "Off"
        case .notSupported: return "\u{2014}"
        @unknown default: return "Unknown"
        }
    }

    private static var versionText: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "0"
        let build = info?["CFBundleVersion"] as? String ?? "0"
        return "\(version) (\(build))"
    }

    // MARK: Actions

    private func forget() {
        Task {
            do {
                try await model.forgetLink()
                dismiss()
            } catch let failure as KeychainStore.Failure {
                problem = "Couldn't remove the link from the Keychain (\(failure.message))."
            } catch {
                problem = "Couldn't remove the link."
            }
        }
    }

    private func clearCache() {
        Task {
            await pages.clearCache()
            cache = await pages.cacheSummary()
        }
    }

    private func saveRegistrationURL() {
        let text = registrationURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            push.registrationURLString = PushRegistrar.defaultRegistrationURL
            registrationURLText = push.registrationURLString
            return
        }
        guard let url = URL(string: text), url.scheme?.lowercased() == "https", url.host != nil else {
            problem = "That needs to be a full https:// address."
            return
        }
        push.registrationURLString = text
    }
}
