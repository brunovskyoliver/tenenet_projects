#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import unicodedata
from pathlib import Path


OUTPUT_HEADERS = [
    "employee_name",
    "employee_source_row",
    "raw_manager",
    "parent_id_import_value",
    "manager_status",
    "matched_manager_name",
    "matched_manager_source_row",
    "matched_manager_set",
]


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def fold_text(value: str) -> str:
    text = normalize_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def aliases(name: str) -> set[str]:
    normalized = normalize_text(name)
    if not normalized:
        return set()
    parts = normalized.split()
    result = {fold_text(normalized)}
    if len(parts) == 2:
        result.add(f"{fold_text(parts[1])} {fold_text(parts[0])}")
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_lookup(rows: list[dict[str, str]], row_set: str) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in rows:
        for alias in aliases(row["name"]):
            lookup.setdefault(alias, {
                "name": row["name"],
                "source_row": row.get("x_source_row", ""),
                "set": row_set,
            })
    return lookup


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ready_import_dir", type=Path)
    args = parser.parse_args()

    ready_dir = args.ready_import_dir
    if not (ready_dir / "hr_employee_import_ready.csv").exists():
        candidate = ready_dir / "ready-import"
        if (candidate / "hr_employee_import_ready.csv").exists():
            ready_dir = candidate

    ready_rows = read_csv(ready_dir / "hr_employee_import_ready.csv")
    excluded_rows = read_csv(ready_dir / "hr_employee_import_excluded.csv")

    ready_lookup = build_lookup(ready_rows, "ready")
    excluded_lookup = build_lookup(excluded_rows, "excluded")

    status_rows: list[dict[str, str]] = []
    for row in ready_rows:
        raw_manager = normalize_text(row.get("x_raw_manager", ""))
        parent_import_value = row.get("parent_id/id", "")

        matched = None
        matched_set = ""
        if raw_manager:
            for alias in aliases(raw_manager):
                matched = ready_lookup.get(alias)
                if matched:
                    matched_set = "ready"
                    break
                matched = excluded_lookup.get(alias)
                if matched:
                    matched_set = "excluded"
                    break

        if not raw_manager:
            manager_status = "no_manager_in_source"
        elif matched_set == "ready":
            manager_status = "manager_in_ready_import"
        elif matched_set == "excluded":
            manager_status = "manager_excluded_by_review"
        else:
            manager_status = "manager_unresolved"

        status_rows.append(
            {
                "employee_name": row["name"],
                "employee_source_row": row.get("x_source_row", ""),
                "raw_manager": raw_manager,
                "parent_id_import_value": parent_import_value,
                "manager_status": manager_status,
                "matched_manager_name": matched["name"] if matched else "",
                "matched_manager_source_row": matched["source_row"] if matched else "",
                "matched_manager_set": matched_set,
            }
        )

    output_path = ready_dir / "parent_link_status.csv"
    write_csv(output_path, status_rows)

    counts: dict[str, int] = {}
    for row in status_rows:
        counts[row["manager_status"]] = counts.get(row["manager_status"], 0) + 1

    print(f"parent_link_status={output_path}")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")


if __name__ == "__main__":
    main()
