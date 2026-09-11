//  Brand.swift
//  Compiled into BOTH targets (app and widget) via ios/Shared.
//
//  The design tokens of engine/ui.py, transcribed for native chrome. The web
//  pages own the design system; this file only repeats the handful of values
//  the native shell needs so the chrome around the web view and the widget
//  read as the same product.
//
//  Rules carried over from ui.py, verbatim in spirit:
//    - ONE gold accent (#F2B722). It is the mark, the rules and the fills.
//    - The top bar is navy (#101B33) in BOTH themes.
//    - No green, no red anywhere. ui.py says "positive" is ink-blue and
//      "negative" is taupe; native chrome needs neither, it says status in
//      words ("Offline", "Saved copy", "Live").
//
//  The values are literal hex so this file has no dependency on the asset
//  catalogs (which carry the same numbers under Navy / Gold / Paper).

import SwiftUI
import UIKit

enum Brand {
    /// The product name as it is set in the top bar of every page.
    static let wordmark = "GRADED TAKES"

    // MARK: Fixed tokens (identical in light and dark)

    static let navy = Color(hex: 0x101B33)       // nav ground, ink on paper, chip ink
    static let gold = Color(hex: 0xF2B722)       // the identity gold: the mark, rules, START fills
    static let paper = Color(hex: 0xF4F2EC)      // the light canvas
    static let navText = Color(hex: 0xEAF0FA)    // text on navy
    static let navRaised = Color(hex: 0x1B2B4D)  // a raised panel on navy
    static let navLine = Color(hex: 0x34497A)    // hairline on navy
    static let goldInk = Color(hex: 0x8F6606)    // text-safe gold on paper (AA on white)
    static let washHot = Color(hex: 0xFFF3D1)    // the warm wash behind a note that needs reading

    // MARK: Theme-following tokens (light / dark, from ui.py's two palettes)

    static let ground = Color(light: 0xF4F2EC, dark: 0x0D1730)
    static let panel = Color(light: 0xFFFFFF, dark: 0x14213D)
    static let raised = Color(light: 0xF8F7F3, dark: 0x1B2B4D)
    static let ink = Color(light: 0x101B33, dark: 0xEAF0FA)
    static let muted = Color(light: 0x5B6478, dark: 0x9AA9C7)
    static let hairline = Color(light: 0xE4E1D8, dark: 0x27395E)

    // MARK: UIKit twins for the few places that need a UIColor

    static let uiNavy = UIColor(hex: 0x101B33)
    static let uiGold = UIColor(hex: 0xF2B722)
    static let uiPaper = UIColor(hex: 0xF4F2EC)
    static let uiGround = UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(hex: 0x0D1730) : UIColor(hex: 0xF4F2EC)
    }
}

/// The app mark: `.wr-mark-sq` from engine/ui.py drawn large - a gold square
/// with a radius of side/12, rotated 45 degrees, on navy. Same geometry as
/// design/icon.svg, so the widget's mark and the home-screen icon agree.
/// `size` is the diagonal, the width the eye actually reads.
struct DiamondMark: View {
    var size: CGFloat = 14

    var body: some View {
        let side = size / 2.squareRoot()
        RoundedRectangle(cornerRadius: side / 12, style: .circular)
            .fill(Brand.gold)
            .frame(width: side, height: side)
            .rotationEffect(.degrees(45))
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

extension Color {
    /// `Color(hex: 0x101B33)` - an opaque sRGB colour from a 24-bit literal.
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }

    /// A colour that follows the system appearance, one literal per theme.
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light)
        })
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}
