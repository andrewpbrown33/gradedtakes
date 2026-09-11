//  main.swift - fixtures for PageMarkup.stamp (ios/GradedTakes/Web/PageMarkup.swift).
//
//  Run with  ios/tools/page_markup_test.sh  - it compiles this file together
//  with PageMarkup.swift using the command-line Swift compiler (no Xcode
//  project, no simulator) and runs it. Prints "CHECKS PASSED" and exits 0
//  when every fixture matches, else lists the failures and exits 1.

import Foundation

var failures: [String] = []
var passed = 0

@MainActor func check(_ name: String, _ input: String, theme: PageMarkup.Theme, expect: String) {
    let out = PageMarkup.stamp(Data(input.utf8), theme: theme)
    let got = String(decoding: out, as: UTF8.self)
    if got == expect {
        passed += 1
    } else {
        failures.append("\(name)\n    input:  \(input.debugDescription)\n    expect: \(expect.debugDescription)\n    got:    \(got.debugDescription)")
    }
}

@MainActor func checkUntouched(_ name: String, _ input: String, theme: PageMarkup.Theme = .dark) {
    let bytes = Data(input.utf8)
    let out = PageMarkup.stamp(bytes, theme: theme)
    if out == bytes {
        passed += 1
    } else {
        failures.append("\(name): expected byte-identical pass-through\n    input: \(input.debugDescription)\n    got:   \(String(decoding: out, as: UTF8.self).debugDescription)")
    }
}

// ---- the five fixtures the brief names -------------------------------------

check("bare <html>",
      "<!doctype html>\n<html><head></head><body>hi</body></html>", theme: .dark,
      expect: "<!doctype html>\n<html data-app=\"ios\" data-theme=\"dark\"><head></head><body>hi</body></html>")

check("<html lang=\"en\">",
      "<!doctype html>\n<html lang=\"en\"><head>", theme: .dark,
      expect: "<!doctype html>\n<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\"><head>")

check("<html data-theme=\"light\" lang=\"en\"> replaces the theme in place",
      "<!doctype html>\n<html data-theme=\"light\" lang=\"en\"><head>", theme: .dark,
      expect: "<!doctype html>\n<html data-theme=\"dark\" lang=\"en\" data-app=\"ios\"><head>")

check("uppercase <HTML>",
      "<!DOCTYPE HTML>\n<HTML><HEAD></HEAD></HTML>", theme: .light,
      expect: "<!DOCTYPE HTML>\n<HTML data-app=\"ios\" data-theme=\"light\"><HEAD></HEAD></HTML>")

checkUntouched("no <html> tag at all",
               "<!doctype html>\n<head><title>x</title></head><body><p>html</p></body>")

// ---- and the edges around them ---------------------------------------------

check("light theme",
      "<html lang=\"en\">", theme: .light,
      expect: "<html lang=\"en\" data-app=\"ios\" data-theme=\"light\">")

check("existing data-app is kept as written",
      "<html data-app=\"web\" lang=\"en\">", theme: .dark,
      expect: "<html data-app=\"web\" lang=\"en\" data-theme=\"dark\">")

check("data-theme with single quotes",
      "<html data-theme='light'>", theme: .dark,
      expect: "<html data-theme=\"dark\" data-app=\"ios\">")

check("data-theme unquoted",
      "<html lang=en data-theme=light class=x>", theme: .dark,
      expect: "<html lang=en data-theme=\"dark\" class=x data-app=\"ios\">")

check("data-theme case-insensitive and duplicated: one survives",
      "<html DATA-THEME=\"light\" data-theme=\"dark\">", theme: .light,
      expect: "<html data-theme=\"light\" data-app=\"ios\">")

check("attributes across lines and odd spacing are preserved",
      "<html\n  lang = \"en\"\n  data-quiet=\"1\"\n>", theme: .dark,
      expect: "<html lang = \"en\" data-quiet=\"1\" data-app=\"ios\" data-theme=\"dark\">")

check("only the first tag is touched; a later <html> in prose stays",
      "<html lang=\"en\"><body><code>&lt;html&gt;</code> <html> and <html data-theme=\"light\"></body>", theme: .dark,
      expect: "<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\"><body><code>&lt;html&gt;</code> <html> and <html data-theme=\"light\"></body>")

check("an <html inside a leading comment is skipped",
      "<!-- <html data-theme=\"light\"> -->\n<html lang=\"en\">", theme: .dark,
      expect: "<!-- <html data-theme=\"light\"> -->\n<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\">")

check("<htmlx> is not the html tag",
      "<htmlx><html>", theme: .dark,
      expect: "<htmlx><html data-app=\"ios\" data-theme=\"dark\">")

check("a > inside a quoted attribute does not end the tag",
      "<html title=\"a>b\" lang=\"en\">", theme: .dark,
      expect: "<html title=\"a>b\" lang=\"en\" data-app=\"ios\" data-theme=\"dark\">")

check("self-closing slash is kept",
      "<html lang=\"en\"/>", theme: .dark,
      expect: "<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\"/>")

check("non-ASCII bytes either side survive intact",
      "<!-- Kid\u{2019}s Table -->\n<html lang=\"en\"><title>caf\u{E9} \u{2014} \u{1F3C8}</title>", theme: .dark,
      expect: "<!-- Kid\u{2019}s Table -->\n<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\"><title>caf\u{E9} \u{2014} \u{1F3C8}</title>")

checkUntouched("empty document", "")
checkUntouched("unterminated tag", "<html lang=\"en\"")
checkUntouched("only a doctype", "<!doctype html>\n")
checkUntouched("html only inside an unterminated comment", "<!-- <html> ")

// ---- the shape the renderers actually emit ---------------------------------

check("engine/ui.py shape: <!doctype html>\\n<html lang=\"en\"><head>",
      "<!doctype html>\n<html lang=\"en\"><head>\n<meta charset=\"utf-8\">\n<meta name=\"referrer\" content=\"no-referrer\">", theme: .light,
      expect: "<!doctype html>\n<html lang=\"en\" data-app=\"ios\" data-theme=\"light\"><head>\n<meta charset=\"utf-8\">\n<meta name=\"referrer\" content=\"no-referrer\">")

check("stamping twice is idempotent apart from the theme",
      "<html lang=\"en\" data-app=\"ios\" data-theme=\"light\">", theme: .dark,
      expect: "<html lang=\"en\" data-app=\"ios\" data-theme=\"dark\">")

// ---- report ------------------------------------------------------------------

if failures.isEmpty {
    print("page_markup: \(passed) fixtures ok")
    print("CHECKS PASSED")
    exit(0)
} else {
    print("page_markup: \(passed) ok, \(failures.count) FAILED")
    for f in failures { print("  FAIL \(f)") }
    exit(1)
}
