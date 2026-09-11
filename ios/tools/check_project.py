#!/usr/bin/env python3
"""Validate ios/GradedTakes.xcodeproj without Xcode. Standard library only.

Converts project.pbxproj to JSON with plutil, walks the group tree to
resolve every file reference to a path on disk, and checks the build-phase
membership that Xcode would only complain about at build time:
  - every referenced file exists (missing Swift files are the usual case
    when sources land after the project was generated)
  - Info.plist and .entitlements are in NO build phase
  - PrivacyInfo.xcprivacy and Assets.xcassets are in Copy Bundle Resources
  - the app embeds the widget .appex
  - the entitlements / bundle-id / team settings are what project.yml says
Exit 1 on any hard failure; missing optional sources are reported, not fatal.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IOS = os.path.dirname(HERE)
PBX = os.path.join(IOS, "GradedTakes.xcodeproj", "project.pbxproj")


def load():
    out = subprocess.check_output(["plutil", "-convert", "json", "-o", "-", PBX])
    return json.loads(out)["objects"]


def main():
    objs = load()
    root_id = json.loads(subprocess.check_output(
        ["plutil", "-convert", "json", "-o", "-", PBX]))["rootObject"]
    project = objs[root_id]
    main_group = project["mainGroup"]

    # ---- resolve every file reference through the group tree ---------------
    paths = {}                                 # fileRef id -> path on disk
    def walk(gid, base):
        g = objs[gid]
        st = g.get("sourceTree", "<group>")
        p = g.get("path")
        if st == "<group>":
            here = os.path.join(base, p) if p else base
        elif st == "SOURCE_ROOT":
            here = os.path.join(IOS, p) if p else IOS
        else:
            here = None                         # BUILT_PRODUCTS_DIR, SDKROOT: not on disk
        if g["isa"] in ("PBXGroup", "PBXVariantGroup"):
            for c in g.get("children", []):
                walk(c, here if here is not None else base)
        elif g["isa"] == "PBXFileReference":
            if here is not None and g.get("sourceTree") not in ("BUILT_PRODUCTS_DIR", "SDKROOT", "DEVELOPER_DIR"):
                paths[gid] = os.path.normpath(here)
    walk(main_group, IOS)

    failures, notes = [], []
    print("File references resolved: %d" % len(paths))
    for fid, p in sorted(paths.items(), key=lambda kv: kv[1]):
        rel = os.path.relpath(p, IOS)
        exists = os.path.exists(p)
        print("  %s %s" % ("ok     " if exists else "MISSING", rel))
        if not exists:
            failures.append("missing on disk: %s" % rel)

    # ---- build-phase membership -------------------------------------------
    def phase_files(target, isa):
        out = []
        for ph in objs[target]["buildPhases"]:
            if objs[ph]["isa"] == isa:
                for bf in objs[ph].get("files", []):
                    ref = objs[bf].get("fileRef")
                    if ref in paths:
                        out.append(os.path.relpath(paths[ref], IOS))
                    elif ref:
                        out.append(objs[ref].get("path") or objs[ref].get("name"))
        return out

    targets = {objs[t]["name"]: t for t in project["targets"]}
    for want in ("GradedTakes", "GradedTakesWidget"):
        if want not in targets:
            failures.append("target %s not in project" % want)
    print("Targets: %s" % ", ".join(sorted(targets)))

    for name, tid in sorted(targets.items()):
        srcs = phase_files(tid, "PBXSourcesBuildPhase")
        res = phase_files(tid, "PBXResourcesBuildPhase")
        print("%s: %d Swift source(s), %d resource(s)" % (name, len(srcs), len(res)))
        for s in srcs:
            print("    compile   %s" % s)
        for r in res:
            print("    resource  %s" % r)
        if not srcs:
            notes.append("%s has NO Swift sources yet - Xcode will open, but the target cannot build" % name)
        for bad in srcs + res:
            b = os.path.basename(bad)
            if b == "Info.plist" or b.endswith(".entitlements"):
                failures.append("%s: %s must not be in a build phase" % (name, bad))
        if not any(r.endswith("PrivacyInfo.xcprivacy") for r in res):
            failures.append("%s: PrivacyInfo.xcprivacy not in Copy Bundle Resources" % name)
        if not any(r.endswith("Assets.xcassets") for r in res):
            failures.append("%s: Assets.xcassets not in Copy Bundle Resources" % name)

    # ---- the app embeds the widget ----------------------------------------
    app = targets.get("GradedTakes")
    if app:
        embedded = []
        for ph in objs[app]["buildPhases"]:
            o = objs[ph]
            if o["isa"] == "PBXCopyFilesBuildPhase" and str(o.get("dstSubfolderSpec")) == "13":
                for bf in o.get("files", []):
                    embedded.append(objs[objs[bf]["fileRef"]].get("path"))
        print("App embeds (PlugIns): %s" % (embedded or "NOTHING"))
        if "GradedTakesWidget.appex" not in embedded:
            failures.append("GradedTakesWidget.appex is not embedded in the app")
        deps = [objs[objs[d]["target"]]["name"] for d in objs[app].get("dependencies", [])]
        if "GradedTakesWidget" not in deps:
            failures.append("app does not depend on the widget target")

    # ---- build settings that must match the contract ----------------------
    expect = {
        "GradedTakes": {"PRODUCT_BUNDLE_IDENTIFIER": "com.gradedtakes.app",
                        "CODE_SIGN_ENTITLEMENTS": "GradedTakes/GradedTakes.entitlements",
                        "INFOPLIST_FILE": "GradedTakes/Info.plist",
                        "TARGETED_DEVICE_FAMILY": "1",          # iPhone only, see docs/APPSTORE.md
                        "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon"},
        "GradedTakesWidget": {"PRODUCT_BUNDLE_IDENTIFIER": "com.gradedtakes.app.widget",
                              "CODE_SIGN_ENTITLEMENTS": "GradedTakesWidget/GradedTakesWidget.entitlements",
                              "INFOPLIST_FILE": "GradedTakesWidget/Info.plist",
                              "TARGETED_DEVICE_FAMILY": "1",
                              "SKIP_INSTALL": "YES"},
    }
    for name, tid in targets.items():
        cl = objs[objs[tid]["buildConfigurationList"]]
        for cid in cl["buildConfigurations"]:
            conf = objs[cid]
            bs = conf["buildSettings"]
            for k, v in expect.get(name, {}).items():
                if bs.get(k) != v:
                    failures.append("%s/%s: %s = %r, expected %r" % (name, conf["name"], k, bs.get(k), v))
            ent = bs.get("CODE_SIGN_ENTITLEMENTS")
            if ent and not os.path.exists(os.path.join(IOS, ent)):
                failures.append("%s: entitlements file %s missing" % (name, ent))
    pl = objs[project["buildConfigurationList"]]
    for cid in pl["buildConfigurations"]:
        bs = objs[cid]["buildSettings"]
        for k in ("SWIFT_VERSION", "SWIFT_STRICT_CONCURRENCY", "SWIFT_DEFAULT_ACTOR_ISOLATION",
                  "IPHONEOS_DEPLOYMENT_TARGET", "TARGETED_DEVICE_FAMILY", "DEVELOPMENT_TEAM",
                  "MARKETING_VERSION", "CURRENT_PROJECT_VERSION"):
            print("  [%s] %s = %r" % (objs[cid]["name"], k, bs.get(k)))
        if not bs.get("DEVELOPMENT_TEAM"):
            notes.append("DEVELOPMENT_TEAM is empty - fill it in project.yml before building for a device")

    print()
    for n in notes:
        print("NOTE  " + n)
    for f in failures:
        print("FAIL  " + f)
    print("RESULT: %s" % ("FAIL" if failures else "OK"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
