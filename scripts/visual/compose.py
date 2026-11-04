"""Render complete diagnostic comparisons; missing/invalid captures still fail."""
import argparse
import html
import json
import re
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

from element_parity import expected_cases


CLIENTS = ("reference", "windows", "macos")


def comparison_targets(spec, matrices, matrix_unknown=False):
    """Resolve actual receipts, never derive acceptance scope from present PNGs."""
    valid = matrices <= {"full", "smoke"} and len(matrices) == 1 and not matrix_unknown
    matrix = next(iter(matrices)) if valid else None
    diagnostic_matrix = matrix or "full"
    cases = {scene + ".png": viewport for scene, viewport in expected_cases(spec, diagnostic_matrix).items()}
    return matrix, diagnostic_matrix, cases


def read_receipts(source, names):
    receipts, errors, matrices, matrix_unknown = {}, [], set(), False
    for client in CLIENTS:
        receipts[client] = []
        paths = sorted((source / client).glob("capture-complete*.json"))
        if not paths:
            errors.append({"client": client, "reason": "No actual capture-complete receipt"})
            matrix_unknown = True
        count, count_known = 0, True
        for path in paths:
            try:
                receipt = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(receipt, dict):
                    raise ValueError("Capture receipt is not an object")
            except (OSError, ValueError) as error:
                errors.append({"client": client, "file": path.name, "reason": "Cannot read actual receipt: " + str(error)})
                matrix_unknown = True
                count_known = False
                continue
            receipts[client].append({"file": path.name, "receipt": receipt})
            matrix = receipt.get("matrix")
            if not isinstance(matrix, str) or matrix not in ("full", "smoke"):
                errors.append({"client": client, "file": path.name, "reason": "Unknown actual receipt matrix", "matrix": matrix})
                matrix_unknown = True
            else:
                matrices.add(matrix)
            actual_count = receipt.get("count")
            if type(actual_count) is not int or actual_count < 0:
                errors.append({"client": client, "file": path.name, "reason": "Invalid actual capture count", "count": actual_count})
                count_known = False
            else:
                count += actual_count
            if receipt.get("errors"):
                errors.append({"client": client, "file": path.name, "reason": "Capture producer recorded errors", "errors": receipt["errors"]})
        if count_known and count != len(names[client]):
            errors.append({"client": client, "reason": "Capture receipt count does not match actual PNG files",
                           "receipt_count": count, "png_count": len(names[client])})
    if len(matrices) != 1:
        errors.append({"reason": "Capture receipts do not establish one common matrix", "observed_matrices": sorted(matrices)})
    return receipts, errors, matrices, matrix_unknown


def diagnostic_placeholder(size, client, status, reason):
    image = Image.new("RGB", size, "#fff1f0")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0] - 1, size[1] - 1), outline="#c2412d", width=3)
    font = ImageFont.load_default(size=18)
    title = f"CAPTURE {status.upper()} — {client}"
    lines = [title, "DIAGNOSTIC PLACEHOLDER — NOT A CAPTURE", ""]
    lines.extend(textwrap.wrap(reason, width=max(16, min(100, size[0] // 10))))
    draw.multiline_text((18, 22), "\n".join(lines), fill="#922b21", font=font, spacing=8)
    return image


def read_image(path, viewport, client):
    size = (viewport["width"], viewport["height"])
    record = {"client": client, "source_file": path.name, "status": "missing", "actual_size": None,
              "expected_size": list(size), "placeholder": True}
    if not path.is_file():
        record["reason"] = "No actual PNG exists for this client and scene."
    elif viewport.get("unmeasured_filename"):
        record.update(status="invalid", reason="Filename does not identify a measured viewport; no capture dimensions are inferred.")
    else:
        try:
            with Image.open(path) as original:
                original.load()
                record["actual_size"] = list(original.size)
                if original.size != size:
                    record.update(status="invalid", reason=f"Actual PNG dimensions {original.size} differ from requested {size}; image was not resized.")
                else:
                    record.update(status="captured", placeholder=False, reason=None)
                    return original.convert("RGB"), record
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            record.update(status="invalid", reason="Actual PNG cannot be decoded: " + str(error))
    record["placeholder_label"] = f"CAPTURE {record['status'].upper()} — {client}"
    return diagnostic_placeholder(size, client, record["status"], record["reason"]), record


def compose(source, output, spec=None):
    if spec is None:
        spec = json.loads((Path(__file__).parent / "scenes.json").read_text(encoding="utf-8"))
    names = {client: {path.name for path in (source / client).glob("*.png")} for client in CLIENTS}
    receipts, receipt_errors, matrices, matrix_unknown = read_receipts(source, names)
    matrix, diagnostic_matrix, required = comparison_targets(spec, matrices, matrix_unknown)
    observed = set.union(*names.values())
    required_names = set(required)
    missing_required = {client: sorted(required_names - names[client]) for client in CLIENTS}
    missing = {client: sorted((required_names | observed) - names[client]) for client in CLIENTS}
    extra = {client: sorted(names[client] - required_names) for client in CLIENTS}
    targets = dict(required)
    for name in sorted(observed - required_names):
        match = re.search(r"-(\d+)x(\d+)-", name)
        # Unexpected PNGs remain visible in the diagnostic index. A malformed
        # filename cannot supply a viewport and receives an explicit invalid slot.
        width, height = map(int, match.groups()) if match else spec["sizes"][0]
        if width <= 0 or height <= 0:
            match = None
            width, height = spec["sizes"][0]
        targets[name] = {"width": width, "height": height, "unmeasured_filename": match is None}
    output.mkdir(parents=True, exist_ok=True)
    rows, scenes, image_errors = [], [], []
    complete = 0
    for name, viewport in sorted(targets.items()):
        images, columns = [], []
        for client in CLIENTS:
            image, record = read_image(source / client / name, viewport, client)
            images.append(image)
            columns.append(record)
            if record["status"] == "invalid":
                image_errors.append({"scene": name, **record})
        is_complete = all(column["status"] == "captured" for column in columns)
        complete += is_complete
        width, height = viewport["width"], viewport["height"]
        with Image.new("RGB", (width * len(CLIENTS) + 32, height + 44), "#dedbd4") as canvas:
            draw = ImageDraw.Draw(canvas)
            left = 0
            for client, image, record in zip(CLIENTS, images, columns):
                draw.text((left + 12, 14), client.upper() + " / " + record["status"].upper(), fill="#1b1b1a")
                canvas.paste(image, (left, 44))
                image.close()
                left += width + 16
            canvas.save(output / name)
        scene = {"file": name, "required": name in required_names, "complete_actual_captures": is_complete,
                 "columns": columns}
        scenes.append(scene)
        details = '<ul>' + ''.join('<li>' + html.escape(column["client"] + ': ' + column["status"]
            + (' — ' + column["reason"] if column["reason"] else ' — original-size actual PNG')) + '</li>' for column in columns) + '</ul>'
        rows.append(f'<figure><figcaption>{html.escape(name)}' + ('' if name in required_names else ' — EXTRA, OUTSIDE REQUIRED MATRIX')
            + '</figcaption>' + details + f'<a href="{html.escape(name, quote=True)}"><img loading="lazy" src="{html.escape(name, quote=True)}"></a></figure>')
    passed = bool(required) and matrix is not None and not receipt_errors and not image_errors and not any(missing.values()) and not any(extra.values())
    coverage = {"matrix": matrix, "diagnostic_matrix": diagnostic_matrix,
                "matrix_resolution": "Actual receipts agree" if matrix is not None else "Unknown/conflicting receipts: full spec retained for diagnosis, never accepted as the observed matrix",
                "observed_receipt_matrices": sorted(matrices), "required_comparisons": len(required), "comparisons": len(scenes),
                "comparisons_quantity": "Diagnostic composites, including clearly labeled placeholders; not a successful capture count",
                "complete_actual_capture_comparisons": complete, "missing": missing, "missing_required": missing_required, "extra": extra,
                "receipt_errors": receipt_errors, "receipts": receipts, "image_errors": image_errors, "scenes": scenes,
                "capture_validation_passed": passed, "visual_acceptance": "requires human review",
                "placeholder_policy": "Missing or invalid slots are explicit diagnostic placeholders, never captured UI or acceptance evidence."}
    (output / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_link = '<p><a href="raw-artifacts.html">Complete original capture artifacts and exact file inventory</a></p>' if (output / "raw-artifacts.html").is_file() else ''
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Relic visual review</title><style>body{font:14px system-ui;background:#f8f7f5;color:#1b1b1a;margin:24px}img{max-width:100%}figure{margin:0 0 32px}figcaption{padding:12px 0}</style><h1>Reference | Windows | macOS — diagnostic comparisons</h1><p>'
        + ('Capture validation passed; visual acceptance still requires human review.' if passed else 'CAPTURE VALIDATION FAILED. Missing/invalid slots are labeled placeholders, not screenshots or acceptance evidence.')
        + '</p><p><a href="coverage.json">Complete coverage, missing/extra files and receipt errors</a></p>' + raw_link + "\n".join(rows), encoding="utf-8")
    if not passed:
        raise ValueError("Diagnostic comparisons were written, but capture receipt/matrix/image validation failed; see " + str(output / "coverage.json"))
    return coverage


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compose(args.source, args.output)
