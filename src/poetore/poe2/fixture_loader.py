from __future__ import annotations

import csv
from pathlib import Path


COPY_COLUMNS = ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文")


def load_real_copy_rows(csv_source: Path) -> tuple[dict[str, str], ...]:
    """Load real-copy rows and resolve @file cells relative to the CSV."""
    with csv_source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for column in COPY_COLUMNS:
            value = str(row.get(column, ""))
            if not value.startswith("@"):
                continue
            relative = value[1:].strip()
            if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError(f"不正なfixture参照です: {value}")
            row[column] = (csv_source.parent / relative).read_text(encoding="utf-8")
    return tuple(rows)
