"""Join each captured screen as reference | Windows | macOS. Fail on missing images."""
import argparse
import html
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw


def compose(source, output):
    clients = ["reference", "windows", "macos"]
    names = {client: {p.name for p in (source / client).glob("*.png")} for client in clients}
    expected = set.union(*names.values())
    receipts = {client: [json.loads(path.read_text()) for path in (source / client).glob("capture-complete*.json")] for client in clients}
    matrices = {r["matrix"] for group in receipts.values() for r in group}
    if len(matrices) != 1 or any(not receipts[client] or sum(r["count"] for r in receipts[client]) != len(names[client]) for client in clients):
        raise ValueError("Capture receipt count/matrix does not match the actual screenshots")
    matrix = next(iter(matrices))
    spec = json.loads((Path(__file__).parent / "scenes.json").read_text())
    if matrix == "full":
        required = {f"{lang}-{theme}-{width}x{height}-{scene}.png" for lang in spec["languages"] for theme in spec["themes"] for width, height in spec["sizes"] for scene in spec["scenes"]}
        if expected != required:
            raise ValueError(f"Full matrix differs from scenes.json: missing {sorted(required - expected)}, extra {sorted(expected - required)}")
    missing = {client: sorted(expected - names[client]) for client in clients if expected - names[client]}
    if not expected or missing:
        raise ValueError(f"Incomplete visual comparison: {missing or 'no captures'}")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in sorted(expected):
        images = [Image.open(source / client / name).convert("RGB") for client in clients]
        match = re.search(r"-(\d+)x(\d+)-", name)
        if match is None or any(im.size != (int(match[1]), int(match[2])) for im in images):
            raise ValueError("Captured dimensions do not match the requested viewport: " + name)
        widths, heights = [im.width for im in images], [im.height for im in images]
        canvas = Image.new("RGB", (sum(widths) + 32, max(heights) + 44), "#dedbd4")
        draw = ImageDraw.Draw(canvas)
        left = 0
        for client, image in zip(clients, images):
            draw.text((left + 12, 14), client.upper(), fill="#1b1b1a")
            canvas.paste(image, (left, 44))
            left += image.width + 16
        canvas.save(output / name)
        rows.append(f'<figure><figcaption>{html.escape(name)}</figcaption><a href="{name}"><img loading="lazy" src="{name}"></a></figure>')
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Relic visual review</title><style>body{font:14px system-ui;background:#f8f7f5;color:#1b1b1a;margin:24px}img{max-width:100%}figure{margin:0 0 32px}figcaption{padding:12px 0}</style><h1>Reference | Windows | macOS</h1>' + "\n".join(rows), encoding="utf-8")
    (output / "coverage.json").write_text(json.dumps({"matrix": matrix, "comparisons": len(expected), "missing": missing, "visual_acceptance": "requires human review"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compose(args.source, args.output)
