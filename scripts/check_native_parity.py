"""Fail closed on native/reference source coverage and the reviewed flow inventory.

Run in CI. This is a coverage guard, not a substitute for native UI acceptance.
Only implementation .cs/.xaml/.swift files count; tests, prose and parity lists do
not. Literal vocabulary in data-driven native controls counts as a use. A key
without its actual control/flow must still fail the inventory gate.
"""
import argparse
import json
from pathlib import Path
import re

from native_reference_platforms import reference_key_platforms

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "plugins/relic/app/static/app.js"


def reference_contract(text):
    vocabulary = json.loads((ROOT / "plugins/relic/relic_core/locales/en-US.json").read_text(encoding="utf-8"))
    # Include ternary alternatives and data-driven menu/settings keys, not only
    # t('literal'). Prefix lookups expand against the one shared vocabulary.
    literals = set(re.findall(r"['\"]([a-z][a-z0-9_.-]+)['\"]", text))
    keys = literals.intersection(vocabulary)
    prefixes = re.findall(r"\bt(?:n)?\(\s*['\"]([a-z][a-z0-9_.-]*\.)['\"]\s*\+", text)
    keys.update(key for key in vocabulary if any(key.startswith(prefix) for prefix in prefixes))
    html = (ROOT / "plugins/relic/app/static/index.html").read_text(encoding="utf-8")
    keys.update(re.findall(r'data-i18n(?:-[\w-]+)?="([^"]+)"', html))
    routes = set(re.findall(r"['\"](/api/[a-z-]+(?:/[a-z-]+)*)", text))
    routes.discard("/api/org")  # expanded below; never a callable route
    routes.update("/api/org/{org}" + route for route in re.findall(r"orgPath\(['\"](/[a-z_-]+)", text))
    routes.add("/api/org/{org}")
    for action in re.findall(r"seatAction\(['\"]([a-z_]+)", text):
        routes.add("/api/org/{org}/" + action)
    routes.update(["/api/org/{org}/request", "/api/cc/{id}/read", "/api/cc/{id}/retire", "/api/harnesses/{id}/install"])
    routes.discard("/api/permission"); routes.add("/api/permission/{id}")
    routes.discard("/api/org/{org}/member"); routes.add("/api/org/{org}/member/{member}")
    functions = [(match.group(1), text[:match.start()].count("\n") + 1)
                 for match in re.finditer(r"\bfunction\s+(\w+)\s*\(", text)]
    return keys, routes, functions


def implementation(platform):
    files = [p for p in (ROOT / "native" / platform).rglob("*")
             if p.suffix in (".cs", ".swift", ".xaml")
             and not any(part in ("bin", "obj", ".build", "Tests") or "Tests" in part for part in p.parts)]
    text = "\n".join(p.read_text(encoding="utf-8-sig") for p in files)
    # Remove full-line comments so coverage notes cannot satisfy the check.
    return re.sub(r"(?m)^\s*//.*$", "", text)


def route_present(route, text):
    if route.startswith("/api/org/{org}"):
        action = route.removeprefix("/api/org/{org}").split("/{", 1)[0]
        return '"/api/org/"' in text and (not action or re.search(r'"' + re.escape(action) + r'(?:[?/"]|$)', text) is not None)
    prefix = route.split("/{", 1)[0]
    if prefix not in text:
        return False
    if "{" in route and route.endswith(("/read", "/retire", "/install")):
        return '"' + route.rsplit("}", 1)[1] + '"' in text
    return True


def key_present(key, text):
    if '"' + key + '"' in text:
        return True
    # Both clients use the same finite server state/task values with a shared
    # vocabulary prefix. Require an actual localization call, not a bare list.
    prefixes = re.findall(r'\b(?:T|t)\(\s*"([a-z][a-z0-9_.-]*\.)"\s*\+', text)
    return any(key.startswith(prefix) for prefix in prefixes)


def browser_ui_uses(text):
    # Toolkit dependencies are not UI. Reject browser controls or JS/HTML render
    # calls in client implementation, including a future accidental shell port.
    return sorted(set(re.findall(r"\b(?:WebView2|WKWebView|WebBrowser|BlazorWebView|ExecuteScriptAsync|NavigateToString|evaluateJavaScript|loadHTMLString)\b", text)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/native-parity.json")
    parser.add_argument("--platform", choices=("windows", "macos"), help="Report one client on its development branch; combined gate remains required on native-apps")
    args = parser.parse_args()
    reference = REFERENCE.read_text(encoding="utf-8")
    keys, routes, functions = reference_contract(reference)
    reachability = reference_key_platforms(reference, keys,
        (ROOT / "plugins/relic/app/static/index.html").read_text(encoding="utf-8"))
    allow = json.loads((ROOT / "native/parity-allowlist.json").read_text(encoding="utf-8"))
    docs = (ROOT / "docs/native-apps.md").read_text(encoding="utf-8")
    inventory = dict((name, (windows, macos)) for name, windows, macos in re.findall(
        r"^\| `([^`]+)` \| [^|]+ \| (done|pending) \| (done|pending) \|", docs, re.M))
    result = {"reference_functions": len(functions), "reference_keys": len(keys), "reference_routes": len(routes),
              "reference_platform_keys": {platform: sum(platform in required for required in reachability["key_platforms"].values())
                                          for platform in ("windows", "macos")},
              "reference_key_reachability": reachability}
    platforms = (args.platform,) if args.platform else ("windows", "macos")
    for platform in platforms:
        source = implementation(platform)
        exemptions = dict(allow["keys"], **allow.get("platform_keys", {}).get(platform, {}))
        # This is source-derived reachability, not a platform exemption list.
        # The full key union and every occurrence/guard remain in the report;
        # an unproven occurrence always requires both implementations.
        required_keys = {key for key in keys if platform in reachability["key_platforms"][key]}
        missing_keys = sorted(key for key in required_keys if key not in exemptions and not key_present(key, source))
        missing_routes = sorted(route for route in routes if route not in allow["routes"] and not route_present(route, source))
        column = 0 if platform == "windows" else 1
        missing_flows = [name + "@" + str(line) for name, line in functions
                         if inventory.get(name + "@" + str(line), ("pending", "pending"))[column] != "done"]
        for name, windows, macos in re.findall(r"^\| ([^|]+) \| [^|]+ \| (done|pending) \| (done|pending) \|", docs, re.M):
            if (windows, macos)[column] != "done" and "@" not in name:
                missing_flows.append(name.strip())
        result[platform] = {"missing_keys": missing_keys, "missing_routes": missing_routes,
                            "incomplete_flows": missing_flows, "browser_ui_uses": browser_ui_uses(source)}
    for section in ("keys", "routes"):
        if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in allow[section].values()):
            raise ValueError("Every parity exemption requires a specific native rationale")
    for platform, substitutions in allow.get("platform_keys", {}).items():
        if platform not in ("windows", "macos") or any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in substitutions.values()):
            raise ValueError("Every platform substitution requires a specific native rationale")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # The complete occurrence/guard ledger is in the uploaded JSON, rather than
    # repeating thousands of source receipts in the CI console.
    print(json.dumps({key: value for key, value in result.items() if key != "reference_key_reachability"}, indent=2, ensure_ascii=False))
    return int(any(any(result[p].values()) for p in platforms))


if __name__ == "__main__":
    raise SystemExit(main())
