#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import unicodedata
from pathlib import Path


EXTERNAL_ID_MODULE = "tenenet_projects_import"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def split_employee_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def fold_text(value: str) -> str:
    text = normalize_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def manager_aliases(name: str) -> set[str]:
    normalized = normalize_text(name)
    if not normalized:
        return set()
    aliases = {fold_text(normalized)}
    parts = normalized.split()
    if len(parts) == 2:
        aliases.add(f"{fold_text(parts[1])} {fold_text(parts[0])}")
    return aliases


def employee_aliases(employee) -> set[str]:
    aliases = set()
    aliases.update(manager_aliases(employee.name or ""))
    aliases.update(manager_aliases(employee.legal_name or ""))
    full_name = " ".join(part for part in [employee.first_name or "", employee.last_name or ""] if part)
    aliases.update(manager_aliases(full_name))
    reversed_name = " ".join(part for part in [employee.last_name or "", employee.first_name or ""] if part)
    aliases.update(manager_aliases(reversed_name))
    return {alias for alias in aliases if alias}


def get_external_record(env, model_name: str, xml_name: str):
    model_data = env["ir.model.data"].sudo()
    data = model_data.search([
        ("module", "=", EXTERNAL_ID_MODULE),
        ("name", "=", xml_name),
        ("model", "=", model_name),
    ], limit=1)
    if not data:
        return env[model_name]
    return env[model_name].browse(data.res_id).exists()


def ensure_external_id(env, record, xml_name: str) -> None:
    model_data = env["ir.model.data"].sudo()
    existing = model_data.search([
        ("module", "=", EXTERNAL_ID_MODULE),
        ("name", "=", xml_name),
    ], limit=1)
    values = {
        "module": EXTERNAL_ID_MODULE,
        "name": xml_name,
        "model": record._name,
        "res_id": record.id,
        "noupdate": True,
    }
    if existing:
        existing.write(values)
    else:
        model_data.create(values)


def get_or_create_department(env, row: dict[str, str]):
    department = get_external_record(env, "hr.department", row["id"])
    vals = {"name": row["name"]}
    if department:
        department.write(vals)
    else:
        department = env["hr.department"].search([("name", "=", row["name"])], limit=1)
        if department:
            department.write(vals)
        else:
            department = env["hr.department"].create(vals)
    ensure_external_id(env, department, row["id"])
    return department


def get_or_create_job(env, row: dict[str, str]):
    job = get_external_record(env, "hr.job", row["id"])
    vals = {"name": row["name"]}
    if job:
        job.write(vals)
    else:
        job = env["hr.job"].search([("name", "=", row["name"])], limit=1)
        if job:
            job.write(vals)
        else:
            job = env["hr.job"].create(vals)
    ensure_external_id(env, job, row["id"])
    return job


def get_or_create_work_location(env, xml_name: str, city: str):
    if not xml_name or not city:
        return env["hr.work.location"]

    country = env.ref("base.sk", raise_if_not_found=False)
    partner_xml_name = f"{xml_name}_addr"
    address = get_external_record(env, "res.partner", partner_xml_name)
    address_vals = {
        "name": f"Work address - {city}",
        "type": "other",
        "city": city,
        "country_id": country.id if country else False,
        "company_type": "company",
    }
    if address:
        address.write(address_vals)
    else:
        address = env["res.partner"].search([
            ("name", "=", address_vals["name"]),
            ("city", "=", city),
        ], limit=1)
        if address:
            address.write(address_vals)
        else:
            address = env["res.partner"].create(address_vals)
    ensure_external_id(env, address, partner_xml_name)

    location = get_external_record(env, "hr.work.location", xml_name)
    location_vals = {
        "name": city,
        "company_id": env.company.id,
        "location_type": "other",
        "address_id": address.id,
    }
    if location:
        location.write(location_vals)
    else:
        location = env["hr.work.location"].search([
            ("name", "=", city),
            ("company_id", "=", env.company.id),
        ], limit=1)
        if location:
            location.write(location_vals)
        else:
            location = env["hr.work.location"].create(location_vals)
    ensure_external_id(env, location, xml_name)
    return location


def get_or_create_employee(env, row: dict[str, str], department_map: dict[str, int], job_map: dict[str, int]):
    employee = get_external_record(env, "hr.employee", row["id"])
    first_name, last_name = split_employee_name(row["name"])
    work_location = get_or_create_work_location(env, row.get("address_id/id", ""), row.get("work_location", ""))
    vals = {
        "title_academic": row.get("title_academic") or False,
        "first_name": first_name or False,
        "last_name": last_name or False,
        "job_id": job_map.get(row["job_id/id"]) or False,
        "department_id": department_map.get(row["department_id/id"]) or False,
        "position_catalog_id": job_map.get(row["job_id/id"]) or False,
        "work_email": row.get("work_email") or False,
        "private_phone": row.get("private_phone") or row.get("mobile_phone") or False,
        "work_phone": row.get("work_phone") or False,
        "work_location_id": work_location.id if work_location else False,
        "address_id": work_location.address_id.id if work_location else False,
    }
    vals["name"] = row["name"]

    if employee:
        employee.write(vals)
    else:
        employee = env["hr.employee"]
        if row.get("work_email"):
            employee = env["hr.employee"].search(
                [("work_email", "=", row.get("work_email"))],
                limit=1,
            )
        if not employee:
            employee = env["hr.employee"].search([("name", "=", row["name"])], limit=1)
        if employee:
            employee.write(vals)
        else:
            employee = env["hr.employee"].create(vals)
    ensure_external_id(env, employee, row["id"])
    return employee


def resolve_manager(env, manager_value: str, employee_map: dict[str, int]):
    manager_value = normalize_text(manager_value)
    if not manager_value:
        return env["hr.employee"]

    aliases = manager_aliases(manager_value)

    for employee_xml, employee_id in employee_map.items():
        employee = env["hr.employee"].browse(employee_id).exists()
        if employee and aliases.intersection(employee_aliases(employee)):
            return employee

    employees = env["hr.employee"].search([])
    for employee in employees:
        if aliases.intersection(employee_aliases(employee)):
            return employee
    return env["hr.employee"]


def import_ready_directory(env, csv_dir: Path) -> dict[str, int]:
    departments = read_csv(csv_dir / "hr_department_import_ready.csv")
    jobs = read_csv(csv_dir / "hr_job_import_ready.csv")
    employees = read_csv(csv_dir / "hr_employee_import_ready.csv")

    department_map: dict[str, int] = {}
    for row in departments:
        department = get_or_create_department(env, row)
        department_map[row["id"]] = department.id

    job_map: dict[str, int] = {}
    for row in jobs:
        job = get_or_create_job(env, row)
        job_map[row["id"]] = job.id

    employee_map: dict[str, int] = {}
    for row in employees:
        employee = get_or_create_employee(env, row, department_map, job_map)
        employee_map[row["id"]] = employee.id

    parent_updates = 0
    for row in employees:
        employee = env["hr.employee"].browse(employee_map[row["id"]]).exists()
        if not employee:
            continue

        parent = env["hr.employee"]
        parent_xml = row.get("parent_id/id") or ""
        if parent_xml:
            parent = env["hr.employee"].browse(employee_map.get(parent_xml)).exists()
        if not parent:
            parent = resolve_manager(env, row.get("x_raw_manager") or "", employee_map)
        if employee and parent and employee.parent_id != parent:
            employee.write({"parent_id": parent.id})
            parent_updates += 1

    return {
        "departments": len(department_map),
        "jobs": len(job_map),
        "employees": len(employee_map),
        "parent_updates": parent_updates,
    }


def main() -> None:
    current_env = globals().get("env")
    if current_env is None:
        raise RuntimeError(
            "Odoo env is not available. Run this script from `odoo-bin shell` and pass `init_globals={'env': env}` to runpy.run_path()."
        )

    parser = argparse.ArgumentParser()
    parser.add_argument("csv_dir", type=Path)
    args = parser.parse_args()

    result = import_ready_directory(current_env, args.csv_dir)
    current_env.cr.commit()
    print(f"DEPARTMENTS={result['departments']}")
    print(f"JOBS={result['jobs']}")
    print(f"EMPLOYEES={result['employees']}")
    print(f"PARENT_UPDATES={result['parent_updates']}")


main()
