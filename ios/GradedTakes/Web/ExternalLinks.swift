//  ExternalLinks.swift
//  GradedTakes
//
//  Links that leave the web view. Two steps, from the brief:
//
//   1. UIApplication.open with .universalLinksOnly. For a universal link
//      this launches the ESPN Fantasy or Yahoo Fantasy app if installed -
//      the reader lands in the app where they set lineups, already signed
//      in - and returns false if no app claims it.
//   2. Otherwise SFSafariViewController, presented full screen by
//      MainView. It keeps the reader inside Graded Takes, with Safari's
//      engine, content blockers and Reader. Note it has NOT shared cookies
//      with Safari since iOS 11, so a site login lives inside the sheet
//      (and persists there for this app).
//
//   mailto: / tel: / sms: go straight to the system.
//
//  Either way the navigation starts from native code: there is no
//  document initiating it, so no Referer header exists to carry the token.

import SafariServices
import SwiftUI
import UIKit

enum ExternalLinks {
    /// Opens `url` outside the web view. `presentSafari` is called with the
    /// URL when nothing else claimed it.
    @MainActor
    static func open(_ url: URL, presentSafari: @escaping @MainActor (URL) -> Void) {
        let scheme = url.scheme?.lowercased() ?? ""
        guard scheme == "http" || scheme == "https" else {
            // mailto:, tel:, sms: - the system decides.
            UIApplication.shared.open(url)
            return
        }
        Task { @MainActor in
            let handled = await UIApplication.shared.open(url, options: [.universalLinksOnly: true])
            if !handled {
                presentSafari(url)
            }
        }
    }
}

/// SFSafariViewController for SwiftUI. Present it with
/// `.fullScreenCover { SafariView(url:).ignoresSafeArea() }`.
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let config = SFSafariViewController.Configuration()
        config.entersReaderIfAvailable = false
        config.barCollapsingEnabled = true
        let controller = SFSafariViewController(url: url, configuration: config)
        controller.preferredBarTintColor = Brand.uiNavy
        controller.preferredControlTintColor = Brand.uiGold
        controller.dismissButtonStyle = .done
        return controller
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}
