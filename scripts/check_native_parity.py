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

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "plugins/relic/app/static/app.js"


def reference_contract(text):
    keys = set(re.findall(r"\bt(?:n)?\(\s*['\"]([^'\"]+)['\"]", text))
    keys = {key for key in keys if not key.endswith(".")}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/native-parity.json")
    args = parser.parse_args()
    keys, routes, functions = reference_contract(REFERENCE.read_text(encoding="utf-8"))
    allow = json.loads((ROOT / "native/parity-allowlist.json").read_text(encoding="utf-8"))
    docs = (ROOT / "docs/native-apps.md").read_text(encoding="utf-8")
    inventory = dict((name, (windows, macos)) for name, windows, macos in re.findall(
        r"^\| `([^`]+)` \| [^|]+ \| (done|pending) \| (done|pending) \|", docs, re.M))
    result = {"reference_functions": len(functions), "reference_keys": len(keys), "reference_routes": len(routes)}
    for platform in ("windows", "macos"):
        source = implementation(platform)
        missing_keys = sorted(key for key in keys if key not in allow["keys"] and ('"' + key + '"') not in source)
        missing_routes = sorted(route for route in routes if route not in allow["routes"] and not route_present(route, source))
        column = 0 if platform == "windows" else 1
        missing_flows = [name + "@" + str(line) for name, line in functions
                         if inventory.get(name + "@" + str(line), ("pending", "pending"))[column] != "done"]
        result[platform] = {"missing_keys": missing_keys, "missing_routes": missing_routes, "incomplete_flows": missing_flows}
    for section in ("keys", "routes"):
        if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in allow[section].values()):
            raise ValueError("Every parity exemption requires a specific native rationale")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(any(any(result[p].values()) for p in ("windows", "macos")))


if __name__ == "__main__":
    raise SystemExit(main())
