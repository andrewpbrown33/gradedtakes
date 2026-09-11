//  ShareSheet.swift
//  GradedTakes
//
//  UIActivityViewController for SwiftUI. Two things are ever shared:
//    - the current page as a PDF (the verdict card into the league chat -
//      docs/APPSTORE.md Tier 1 item 5), which carries no link at all
//    - the reader's private page URL, only after an explicit confirmation
//      that names what the link is (MainView)

import SwiftUI
import UIKit

struct ShareItem: Identifiable {
    let id = UUID()
    let items: [Any]
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.excludedActivityTypes = [.assignToContact, .addToReadingList]
        return controller
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
