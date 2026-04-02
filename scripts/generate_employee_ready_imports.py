#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ROW_RE = re.compile(r"^- Row (?P<row>\d+):\s", re.MULTILINE)


def load_excluded_rows(review_report: Path) -> set[str]:
    text = review_report.read_text(encoding="utf-8")
    return {match.group("row") for match in ROW_RE.finditer(text)}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    base_dir = args.base_dir
    output_dir = args.output_dir or (base_dir / "ready-import")
    output_dir.mkdir(parents=True, exist_ok=True)

    employee_path = base_dir / "hr_employee_import.csv"
    job_path = base_dir / "hr_job_import.csv"
    department_path = base_dir / "hr_department_import.csv"
    review_path = base_dir / "employee_cleanup_review.md"

    employee_headers, employees = read_csv(employee_path)
    job_headers, jobs = read_csv(job_path)
    department_headers, departments = read_csv(department_path)
    excluded_rows = load_excluded_rows(review_path)

    ready_employees = [row for row in employees if row["x_source_row"] not in excluded_rows]
    excluded_employees = [row for row in employees if row["x_source_row"] in excluded_rows]
    included_employee_ids = {row["id"] for row in ready_employees}

    removed_parent_links = 0
    for row in ready_employees:
        parent_id = row["parent_id/id"]
        if parent_id and parent_id not in included_employee_ids:
            row["parent_id/id"] = ""
            removed_parent_links += 1
            existing_note = row.get("x_review_note", "").strip()
            extra_note = "parent removed because manager is excluded from import"
            row["x_review_note"] = f"{existing_note}; {extra_note}" if existing_note else extra_note

    used_job_ids = {row["job_id/id"] for row in ready_employees if row["job_id/id"]}
    used_department_ids = {row["department_id/id"] for row in ready_employees if row["department_id/id"]}

    ready_jobs = [row for row in jobs if row["id"] in used_job_ids]
    ready_departments = [row for row in departments if row["id"] in used_department_ids]

    write_csv(output_dir / "hr_employee_import_ready.csv", employee_headers, ready_employees)
    write_csv(output_dir / "hr_employee_import_excluded.csv", employee_headers, excluded_employees)
    write_csv(output_dir / "hr_job_import_ready.csv", job_headers, ready_jobs)
    write_csv(output_dir / "hr_department_import_ready.csv", department_headers, ready_departments)

    summary = "\n".join(
        [
            "# Ready Employee Import Summary",
            "",
            f"- Excluded source rows from review report: {len(excluded_rows)}",
            f"- Employees ready for import: {len(ready_employees)}",
            f"- Employees excluded from import: {len(excluded_employees)}",
            f"- Jobs kept: {len(ready_jobs)}",
            f"- Departments kept: {len(ready_departments)}",
            f"- Parent links blanked because manager was excluded: {removed_parent_links}",
            "",
        ]
    )
    (output_dir / "ready_import_summary.md").write_text(summary, encoding="utf-8")

    print(f"Excluded rows: {len(excluded_rows)}")
    print(f"Ready employees: {len(ready_employees)}")
    print(f"Ready jobs: {len(ready_jobs)}")
    print(f"Ready departments: {len(ready_departments)}")
    print(f"Removed parent links: {removed_parent_links}")


if __name__ == "__main__":
    main()
