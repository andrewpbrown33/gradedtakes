//  OnboardingView.swift
//  GradedTakes
//
//  First launch: one calm screen asking for the private link, in the
//  product's voice. Also presented from Settings > Replace the link (then
//  with a Cancel button). Nothing is fetched until the link is saved;
//  the link is validated by shape only (PrivateLink.parse) so a wrong
//  paste gets a sentence, not a network error.
//
//  PasteButton is used instead of reading UIPasteboard directly: it is the
//  system's own control, it does not trigger the "pasted from" banner, and
//  it never reads the clipboard until the reader taps it.

import SwiftUI

struct OnboardingView: View {
    /// true when presented from Settings over an existing link.
    let isReplacing: Bool

    @Environment(AppModel.self) private var model
    @Environment(LinkStore.self) private var links
    @Environment(\.dismiss) private var dismiss

    @State private var text = ""
    @State private var problem: String?
    @State private var isSaving = false
    @FocusState private var fieldFocused: Bool

    var body: some View {
        ZStack {
            Brand.ground.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    Rectangle()
                        .fill(Brand.gold)
                        .frame(width: 40, height: 3)
                        .clipShape(Capsule())
                        .padding(.top, 12)

                    Text(isReplacing ? "Paste the new link." : "Paste the link you were sent.")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(Brand.ink)

                    Text("Your pages live at an address only you were given. It starts with gradedtakes.com and ends in home.html. Paste the whole thing and the app opens straight into your week.")
                        .font(.body)
                        .foregroundStyle(Brand.ink)

                    field

                    if let problem {
                        Text(problem)
                            .font(.footnote)
                            .foregroundStyle(Brand.goldInk)
                            .accessibilityLabel("Problem: \(problem)")
                    }

                    actions

                    Text("The link is stored in your iPhone's Keychain and never leaves this phone except to fetch your own pages. No account, no password, nothing to pay.")
                        .font(.footnote)
                        .foregroundStyle(Brand.muted)
                        .padding(.top, 8)

                    if let failure = links.lastFailure {
                        Text("Your phone's Keychain didn't answer (\(failure.message)). Unlock the phone and open the app again.")
                            .font(.footnote)
                            .foregroundStyle(Brand.goldInk)
                    }

                    if isReplacing {
                        Text("Replacing the link wipes the saved pages on this phone. The new link's pages take their place on the next open.")
                            .font(.footnote)
                            .foregroundStyle(Brand.muted)
                    }
                }
                .padding(24)
                .frame(maxWidth: 560, alignment: .leading)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .onAppear { if !isReplacing { fieldFocused = true } }
    }

    private var header: some View {
        HStack(spacing: 10) {
            DiamondMark(size: 18)
            Text(Brand.wordmark)
                .font(.system(size: 13, weight: .semibold))
                .tracking(2.2)
                .foregroundStyle(Brand.ink)
            Spacer()
            if isReplacing {
                Button("Cancel") { dismiss() }
                    .font(.body)
                    .tint(Brand.goldInk)
            }
        }
    }

    private var field: some View {
        TextField("https://gradedtakes.com/…/home.html", text: $text, axis: .vertical)
            .lineLimit(2...4)
            .font(.system(.body, design: .monospaced))
            .keyboardType(.URL)
            .textContentType(.URL)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .focused($fieldFocused)
            .onChange(of: text) { _, _ in problem = nil }
            .padding(12)
            .background(Brand.panel, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(fieldFocused ? Brand.gold : Brand.hairline, lineWidth: fieldFocused ? 1.5 : 1)
            )
            .foregroundStyle(Brand.ink)
    }

    private var actions: some View {
        HStack(spacing: 12) {
            PasteButton(payloadType: String.self) { strings in
                if let pasted = strings.first {
                    text = pasted
                    problem = nil
                }
            }
            .labelStyle(.titleAndIcon)
            .buttonBorderShape(.capsule)
            .tint(Brand.navy)

            Spacer()

            Button(action: submit) {
                HStack(spacing: 8) {
                    if isSaving { ProgressView().tint(Brand.navy) }
                    Text(isReplacing ? "Use this link" : "Open my week")
                        .font(.body.weight(.semibold))
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 11)
                .background(Brand.gold, in: Capsule())
                .foregroundStyle(Brand.navy)
            }
            .disabled(isSaving || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    private func submit() {
        guard !isSaving else { return }
        switch PrivateLink.parse(text) {
        case .failure(let error):
            problem = error.message
        case .success(let link):
            isSaving = true
            Task {
                do {
                    try await model.replaceLink(with: link)
                    text = ""
                    if isReplacing { dismiss() }
                } catch let failure as KeychainStore.Failure {
                    problem = "Couldn't save the link to the Keychain (\(failure.message)). Try again after unlocking the phone."
                } catch {
                    problem = "Couldn't save the link. Try again."
                }
                isSaving = false
            }
        }
    }
}
