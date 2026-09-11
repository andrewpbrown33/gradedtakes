//  RootView.swift
//  GradedTakes
//
//  Two states, one switch: no link yet -> the paste screen; a link -> the
//  shell. Forgetting the link in Settings flips it back.

import SwiftUI

struct RootView: View {
    @Environment(LinkStore.self) private var links

    var body: some View {
        Group {
            if links.link != nil {
                MainView()
            } else {
                OnboardingView(isReplacing: false)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: links.link != nil)
    }
}
