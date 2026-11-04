"""Read-only checks against the actual pinned checkout, before compiling its private API user."""
from pathlib import Path
import re

# These are deliberately narrow ABI/serialization assumptions, not an alternative decoder.
SOURCE_REQUIREMENTS = {
    "src/core/SkTextBlobPriv.h": (
        r"kDefault_Positioning\s*=\s*0", r"kHorizontal_Positioning\s*=\s*1",
        r"kFull_Positioning\s*=\s*2", r"kRSXform_Positioning\s*=\s*3",
        r"unsigned\s+scalarsPerGlyph\(\)\s+const", r"uint32_t\*\s+clusters\(\)\s+const",
    ),
    "src/core/SkPictureData.cpp": (
        r"SerializeBehavior::kDoIncludeData", r"procs\.fTypefaceStreamProc\(\*stream,\s*procs\.fTypefaceCtx\)",
        r"tf\s*=\s*SkTypeface::MakeEmpty\(\)",
    ),
    "src/core/SkTypeface.cpp": (
        r"DWriteFontTypeface::FactoryId,\s*DWriteFontTypeface::MakeFromStream",
        r"return\s+SkEmptyTypeface::Make\(\)",
    ),
    "include/core/SkSerialProcs.h": (
        r"SkDeserialTypefaceStreamProc\s*=\s*sk_sp<SkTypeface>\s*\(\*\)\(SkStream&,\s*void\*",
    ),
    "include/utils/SkNoDrawCanvas.h": (
        r"conservative clipping", r"onDrawPicture\([^;]+override\s*\{\}",
    ),
}


def check_source_contract(root: Path) -> dict:
    results, errors = [], []
    for relative, patterns in SOURCE_REQUIREMENTS.items():
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        for pattern in patterns:
            matched = re.search(pattern, text, re.S) is not None
            results.append({"file": relative, "pattern": pattern, "matched": matched})
            if not matched:
                errors.append(f"Pinned source contract not found: {relative}: {pattern}")
    return {"status": "verified" if not errors else "failed", "checks": results, "errors": errors}
