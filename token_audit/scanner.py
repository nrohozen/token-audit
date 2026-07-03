import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ScanResult, TokenRecord


def _parse_timestamp(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def scan_file(path: Path, project: str) -> tuple[list[TokenRecord], int]:
    """Parse one JSONL session file; return (records, skipped_line_count)."""
    records: list[TokenRecord] = []
    skipped = 0

    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    continue

                message = obj.get("message")
                if not isinstance(message, dict):
                    continue

                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue

                model = message.get("model") or ""
                if not isinstance(model, str):
                    model = str(model)

                ts = _parse_timestamp(obj.get("timestamp", ""))
                if ts is None:
                    skipped += 1
                    continue

                tool_names: list[str] = []
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name")
                            if isinstance(name, str) and name:
                                tool_names.append(name)

                cwd = obj.get("cwd")
                if not isinstance(cwd, str):
                    cwd = ""

                records.append(
                    TokenRecord(
                        project=project,
                        session_file=path.name,
                        session_id=obj.get("sessionId") or path.stem,
                        model=model,
                        timestamp=ts,
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cache_creation_tokens=int(
                            usage.get("cache_creation_input_tokens") or 0
                        ),
                        cache_read_tokens=int(
                            usage.get("cache_read_input_tokens") or 0
                        ),
                        cwd=cwd,
                        tool_names=tool_names,
                    )
                )
    except OSError:
        skipped += 1

    return records, skipped


def scan_directory(data_dir: Path) -> ScanResult:
    """Walk all project directories under data_dir and return a ScanResult."""
    all_records: list[TokenRecord] = []
    total_skipped = 0
    scanned_files = 0

    if not data_dir.exists():
        return ScanResult(records=[], skipped_lines=0, scanned_files=0)

    for project_dir in sorted(data_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            recs, skipped = scan_file(jsonl_path, project)
            all_records.extend(recs)
            total_skipped += skipped
            scanned_files += 1

    return ScanResult(
        records=all_records,
        skipped_lines=total_skipped,
        scanned_files=scanned_files,
    )
