//  PageMarkup.swift
//  GradedTakes
//
//  The one edit the app makes to a page's bytes before WebKit sees them.
//  The first <html> tag of every document served through
//  gradedtakes-pages:// is stamped with two attributes:
//
//    data-app="ios"       "you are inside the native shell" - the shell
//                         draws the top bar and the tab bar, so the page
//                         can drop its own (engine/ui.py keys off this).
//                         Added only when absent; a page that already
//                         declares data-app keeps what it says.
//    data-theme="dark"    the phone's appearance at the moment the page
//    data-theme="light"   is served, replacing whatever the renderer wrote,
//                         so the page follows the phone rather than its own
//                         guess. WebView also pushes a new value into the
//                         live document when the appearance changes.
//
//  Robustness rules, each covered by ios/tools/page_markup_test.sh:
//    - the tag is found case-insensitively (<html, <HTML), with or without
//      attributes, and must be a real tag: "<htmlx" does not count
//    - an <html inside a comment before the real tag is skipped
//    - only the FIRST tag is touched; a later "<html>" in prose or a
//      code sample is left byte-for-byte as it was
//    - a document with no <html> tag passes through byte-identical
//    - the tag's own bytes (case, attribute order, quoting) are preserved;
//      only data-theme is rewritten and the two attributes appended
//
//  Pure Foundation, no UIKit: the test script compiles this file with the
//  command-line compiler alone.

import Foundation

enum PageMarkup {
    /// The value the shell declares itself as.
    static let app = "ios"

    enum Theme: String, Sendable {
        case light, dark
    }

    /// `data` with its first <html> tag stamped; `data` unchanged when
    /// there is no such tag.
    static func stamp(_ data: Data, theme: Theme) -> Data {
        guard let tag = firstHTMLTag(in: data) else { return data }
        let original = String(decoding: data[tag.attributesRange], as: UTF8.self)
        let rewritten = rewriteAttributes(original, theme: theme)
        var out = Data(capacity: data.count + 40)
        out.append(data[data.startIndex..<tag.attributesRange.lowerBound])
        out.append(Data(rewritten.utf8))
        out.append(data[tag.attributesRange.upperBound..<data.endIndex])
        return out
    }

    // MARK: Finding the tag

    struct Tag {
        /// The bytes between "<html" and the closing ">" - the attribute text.
        let attributesRange: Range<Data.Index>
    }

    private static let lt = UInt8(ascii: "<")
    private static let gt = UInt8(ascii: ">")
    private static let slash = UInt8(ascii: "/")
    private static let bang = UInt8(ascii: "!")
    private static let dash = UInt8(ascii: "-")
    private static let dquote = UInt8(ascii: "\"")
    private static let squote = UInt8(ascii: "'")

    private static func isSpace(_ b: UInt8) -> Bool {
        b == 0x20 || b == 0x09 || b == 0x0A || b == 0x0D || b == 0x0C
    }

    private static func lower(_ b: UInt8) -> UInt8 {
        (b >= 0x41 && b <= 0x5A) ? b + 0x20 : b
    }

    /// The first real <html ...> tag, skipping <!-- comments -->.
    static func firstHTMLTag(in data: Data) -> Tag? {
        let name: [UInt8] = Array("html".utf8)
        let end = data.endIndex
        var i = data.startIndex
        while i < end {
            guard data[i] == lt else { i += 1; continue }
            // <!-- ... --> : jump past the comment, or give up if unterminated.
            if i + 3 < end, data[i + 1] == bang, data[i + 2] == dash, data[i + 3] == dash {
                guard let close = indexOfCommentClose(in: data, from: i + 4) else { return nil }
                i = close
                continue
            }
            let nameEnd = i + 1 + name.count
            guard nameEnd <= end else { return nil }
            var matches = true
            for (k, c) in name.enumerated() where lower(data[i + 1 + k]) != c {
                matches = false
                break
            }
            if matches, nameEnd < end, isSpace(data[nameEnd]) || data[nameEnd] == gt || data[nameEnd] == slash {
                guard let close = indexOfTagClose(in: data, from: nameEnd) else { return nil }
                return Tag(attributesRange: nameEnd..<close)
            }
            i += 1
        }
        return nil
    }

    private static func indexOfCommentClose(in data: Data, from start: Data.Index) -> Data.Index? {
        var i = start
        while i + 2 < data.endIndex {
            if data[i] == dash, data[i + 1] == dash, data[i + 2] == gt { return i + 3 }
            i += 1
        }
        return nil
    }

    /// The ">" that ends the tag, honouring quoted attribute values.
    private static func indexOfTagClose(in data: Data, from start: Data.Index) -> Data.Index? {
        var i = start
        var quote: UInt8? = nil
        while i < data.endIndex {
            let b = data[i]
            if let q = quote {
                if b == q { quote = nil }
            } else if b == dquote || b == squote {
                quote = b
            } else if b == gt {
                return i
            }
            i += 1
        }
        return nil
    }

    // MARK: Rewriting the attributes

    private struct Attribute {
        let name: String        // lower-cased
        let source: Substring   // as written, name through value
    }

    /// `text` is everything between "<html" and ">". Returns the replacement
    /// for that same span: existing attributes as written, data-theme
    /// rewritten in place (or appended), data-app appended when absent.
    static func rewriteAttributes(_ text: String, theme: Theme) -> String {
        let (attributes, selfClosing) = tokenize(text)
        var parts: [String] = []
        var sawTheme = false
        var sawApp = false
        for attribute in attributes {
            switch attribute.name {
            case "data-theme":
                if !sawTheme {
                    parts.append("data-theme=\"\(theme.rawValue)\"")
                    sawTheme = true
                }
            case "data-app":
                sawApp = true
                parts.append(String(attribute.source))
            default:
                parts.append(String(attribute.source))
            }
        }
        if !sawApp { parts.append("data-app=\"\(app)\"") }
        if !sawTheme { parts.append("data-theme=\"\(theme.rawValue)\"") }
        var out = parts.map { " " + $0 }.joined()
        if selfClosing { out += "/" }
        return out
    }

    /// A small HTML attribute tokenizer: name, optional = and a quoted or
    /// bare value. A lone "/" before the ">" is reported, not kept as an
    /// attribute. Tolerant by design - anything odd becomes an attribute
    /// whose source is preserved verbatim.
    private static func tokenize(_ text: String) -> ([Attribute], Bool) {
        var attributes: [Attribute] = []
        var selfClosing = false
        var i = text.startIndex
        let end = text.endIndex

        func skipSpaces() {
            while i < end, text[i].isWhitespace { i = text.index(after: i) }
        }

        while true {
            skipSpaces()
            guard i < end else { break }
            if text[i] == "/" {
                i = text.index(after: i)
                skipSpaces()
                if i >= end { selfClosing = true }
                continue
            }
            let start = i
            while i < end, !text[i].isWhitespace, text[i] != "=", text[i] != "/" {
                i = text.index(after: i)
            }
            if i == start { i = text.index(after: i); continue }   // a stray "/" mid-tag
            let name = text[start..<i].lowercased()
            var valueEnd = i
            // Optional "= value", with whitespace allowed around the "=".
            var j = i
            while j < end, text[j].isWhitespace { j = text.index(after: j) }
            if j < end, text[j] == "=" {
                j = text.index(after: j)
                while j < end, text[j].isWhitespace { j = text.index(after: j) }
                if j < end, text[j] == "\"" || text[j] == "'" {
                    let q = text[j]
                    j = text.index(after: j)
                    while j < end, text[j] != q { j = text.index(after: j) }
                    if j < end { j = text.index(after: j) }
                } else {
                    while j < end, !text[j].isWhitespace { j = text.index(after: j) }
                }
                valueEnd = j
                i = j
            }
            attributes.append(Attribute(name: name, source: text[start..<valueEnd]))
        }
        return (attributes, selfClosing)
    }
}
