from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.taxonomy.flatten import expand_membership, flatten_themes
from app.taxonomy.loader import TAXONOMY_DIR, bundle_to_frames, default_meta, load_taxonomy_bundle
from app.taxonomy.validate import validate_taxonomy


def export_csv(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    bundle = load_taxonomy_bundle()
    themes, members = bundle_to_frames(bundle)
    themes.to_csv(directory / "themes.csv", index=False)
    members.to_csv(directory / "membership.csv", index=False)
    (directory / "mapping_meta.json").write_text(
        json.dumps(default_meta(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate / export v2 theme taxonomy.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--out", default=str(TAXONOMY_DIR))
    args = parser.parse_args(argv)
    if args.export:
        export_csv(Path(args.out))
        print(f"exported {args.out}")
    bundle = load_taxonomy_bundle(Path(args.out) if Path(args.out).is_dir() else None)
    report = validate_taxonomy(bundle)
    payload = {
        "ok": report.ok,
        "theme_count": report.theme_count,
        "l1": report.l1,
        "l2": report.l2,
        "l3": report.l3,
        "mapped_securities": report.mapped_securities,
        "below_min_members": report.below_min_members,
        "concentrated_exceptions": report.concentrated_exceptions,
        "issues": report.issues,
        "multi_theme_histogram": report.multi_theme_histogram,
        "flatten_check": len(flatten_themes()),
        "membership_rows": len(expand_membership()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
