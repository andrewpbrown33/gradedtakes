//  Connectivity.swift
//  GradedTakes
//
//  Is there a network path right now? NWPathMonitor (Network framework;
//  `final class`, Sendable) answers on its own queue; the answer is hopped
//  to the main actor so SwiftUI can read it. A satisfied path is a
//  necessary condition, not a promise: a fetch that fails is ALSO treated
//  as offline by PageService, which is what the banner keys off.

import Foundation
import Network
import Observation

@MainActor @Observable
final class Connectivity {
    /// True when NWPathMonitor reports a usable path. Starts optimistic so
    /// the first load tries the network before anything is known.
    private(set) var isOnline = true

    /// True on cellular; shown nowhere today, kept for a future "save data" note.
    private(set) var isExpensive = false

    private let monitor = NWPathMonitor()

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            // Extract Sendable facts before crossing to the main actor.
            let online = path.status == .satisfied
            let expensive = path.isExpensive
            Task { @MainActor in
                self?.isOnline = online
                self?.isExpensive = expensive
            }
        }
        monitor.start(queue: DispatchQueue(label: "com.gradedtakes.app.net-monitor"))
    }
}
