from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.soak_evidence import (  # noqa: E402
    build_campaign_evidence,
    read_database_snapshot,
    render_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic read-only shadow-campaign evidence.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-head", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--previous-status")
    args = parser.parse_args()

    status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    previous = json.loads(Path(args.previous_status).read_text(encoding="utf-8")) if args.previous_status else None
    counts, safety = read_database_snapshot(args.database)
    artifact = build_campaign_evidence(
        status=status,
        database_counts=counts,
        database_safety=safety,
        code_head=args.code_head,
        observed_at=datetime.fromisoformat(args.observed_at.replace("Z", "+00:00")),
        previous_status=previous,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shadow-campaign-evidence.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "shadow-campaign-evidence.md").write_text(render_markdown(artifact), encoding="utf-8")
    print(str(output_dir.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
