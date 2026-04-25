from odoo import api, fields, models


class TenenetEmployeeTenenetCost(models.Model):
    _name = "tenenet.employee.tenenet.cost"
    _description = "Náklady zamestnanca – Tenenet (reziduum)"
    _order = "period desc, employee_id"

    CCP_MULTIPLIER = 1.362

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    gross_salary_employee = fields.Monetary(
        string="Celková hrubá mzda zamestnanca",
        currency_field="currency_id",
        help="Celková hrubá mzda zamestnanca za daný mesiac (z mzdovej agendy)",
    )
    total_labor_cost_employee = fields.Monetary(
        string="Celková cena práce zamestnanca",
        currency_field="currency_id",
        help="Celková cena práce zamestnanca za daný mesiac (z mzdovej agendy)",
    )
    imported_from_migration_workbook = fields.Boolean(
        string="Importované z migračného workbooku",
        default=False,
        help="Technický príznak, že mesačné sumáre/hodiny boli prepísané priamo z migračného workbooku.",
    )
    imported_capacity_hours_incl = fields.Float(
        string="Importované hodiny za mesiac vrátane sviatkov",
        digits=(10, 2),
    )
    imported_capacity_hours = fields.Float(
        string="Importované hodiny za mesiac",
        digits=(10, 2),
    )
    imported_total_gross_salary = fields.Monetary(
        string="Importovaná hrubá mzda",
        currency_field="currency_id",
    )
    imported_total_labor_cost = fields.Monetary(
        string="Importovaná celková cena práce",
        currency_field="currency_id",
    )
    imported_worked_hours = fields.Float(
        string="Importované odpracované hodiny",
        digits=(10, 2),
    )
    imported_holidays_hours = fields.Float(
        string="Importované platené sviatky",
        digits=(10, 2),
    )
    imported_vacation_hours = fields.Float(
        string="Importovaná dovolenka",
        digits=(10, 2),
    )
    imported_doctor_hours = fields.Float(
        string="Importovaný lekár",
        digits=(10, 2),
    )
    imported_internal_gross_salary = fields.Monetary(
        string="Importovaná interná hrubá mzda",
        currency_field="currency_id",
    )
    imported_internal_labor_cost = fields.Monetary(
        string="Importovaná interná celková cena práce",
        currency_field="currency_id",
    )
    monthly_gross_salary_target = fields.Monetary(
        string="Cieľ CCP za obdobie",
        currency_field="currency_id",
        compute="_compute_period_targets",
        store=True,
        readonly=True,
    )
    monthly_gross_salary_target_hm = fields.Monetary(
        string="Cieľ HM za obdobie (brutto)",
        currency_field="currency_id",
        compute="_compute_period_targets",
        store=True,
        readonly=True,
    )
    base_workdays = fields.Integer(
        string="Pracovné dni v mesiaci",
        compute="_compute_period_targets",
        store=True,
        readonly=True,
    )
    holiday_workdays = fields.Integer(
        string="Sviatky v pracovných dňoch",
        compute="_compute_period_targets",
        store=True,
        readonly=True,
    )
    effective_workdays = fields.Integer(
        string="Pracovné dni po sviatkoch",
        compute="_compute_period_targets",
        store=True,
        readonly=True,
    )
    project_billed_gross = fields.Monetary(
        string="Fakturovaná hrubá mzda projektom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    project_billed_ccp = fields.Monetary(
        string="Fakturovaná CCP projektom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    hours_covered_hm = fields.Monetary(
        string="Projektom krytá HM podľa hodín",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    hours_covered_ccp = fields.Monetary(
        string="Projektom krytá CCP podľa hodín",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    fixed_ratio_covered_hm = fields.Monetary(
        string="Projektom krytá HM fixným podielom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    fixed_ratio_covered_ccp = fields.Monetary(
        string="Projektom krytá CCP fixným podielom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    tenenet_residual_hm = fields.Monetary(
        string="Reziduum Tenenet – hrubá mzda",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    tenenet_residual_ccp = fields.Monetary(
        string="Reziduum Tenenet – CCP",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )

    _unique_employee_period = models.Constraint(
        "UNIQUE(employee_id, period)",
        "Pre zamestnanca môže existovať len jeden Tenenet nákladový záznam za obdobie.",
    )

    @api.depends(
        "employee_id",
        "period",
        "employee_id.monthly_gross_salary_target",
        "employee_id.tenenet_payroll_contribution_multiplier",
        "employee_id.resource_calendar_id",
        "employee_id.resource_calendar_id.attendance_ids",
        "employee_id.resource_calendar_id.leave_ids",
    )
    def _compute_period_targets(self):
        for rec in self:
            if not rec.employee_id or not rec.period:
                rec.monthly_gross_salary_target = 0.0
                rec.monthly_gross_salary_target_hm = 0.0
                rec.base_workdays = 0
                rec.holiday_workdays = 0
                rec.effective_workdays = 0
                continue
            metrics = rec.employee_id._get_month_workday_metrics(rec.period)
            rec.base_workdays = metrics["base_workdays"]
            rec.holiday_workdays = metrics["holiday_workdays"]
            rec.effective_workdays = metrics["effective_workdays"]
            rec.monthly_gross_salary_target = rec.employee_id._get_effective_monthly_gross_salary_target(rec.period)
            rec.monthly_gross_salary_target_hm = rec.employee_id._get_effective_monthly_gross_salary_target_hm(rec.period)

    @api.depends(
        "employee_id",
        "period",
        "gross_salary_employee",
        "total_labor_cost_employee",
        "employee_id.assignment_ids.timesheet_ids.gross_salary",
        "employee_id.assignment_ids.timesheet_ids.total_labor_cost",
        "employee_id.assignment_ids.timesheet_ids.period",
        "employee_id.monthly_gross_salary_target",
        "employee_id.tenenet_payroll_contribution_multiplier",
        "employee_id.assignment_ids.project_id.salary_funding_mode",
        "employee_id.assignment_ids.allocation_ratio",
        "employee_id.assignment_ids.ratio_month_ids.allocation_ratio",
        "employee_id.assignment_ids.ratio_month_ids.period",
        "employee_id.assignment_ids.date_start",
        "employee_id.assignment_ids.date_end",
        "employee_id.assignment_ids.active",
        "monthly_gross_salary_target",
        "monthly_gross_salary_target_hm",
    )
    def _compute_residual(self):
        for rec in self:
            if not rec.employee_id or not rec.period:
                rec.project_billed_gross = 0.0
                rec.project_billed_ccp = 0.0
                rec.hours_covered_hm = 0.0
                rec.hours_covered_ccp = 0.0
                rec.fixed_ratio_covered_hm = 0.0
                rec.fixed_ratio_covered_ccp = 0.0
                rec.tenenet_residual_hm = 0.0
                rec.tenenet_residual_ccp = 0.0
                continue

            coverage = rec._get_project_salary_contributions()
            billed_gross = coverage["total_hm"]
            billed_ccp = coverage["total_ccp"]

            rec.project_billed_gross = billed_gross
            rec.project_billed_ccp = billed_ccp
            rec.hours_covered_hm = coverage["hours_hm"]
            rec.hours_covered_ccp = coverage["hours_ccp"]
            rec.fixed_ratio_covered_hm = coverage["fixed_ratio_hm"]
            rec.fixed_ratio_covered_ccp = coverage["fixed_ratio_ccp"]
            target_ccp = rec.monthly_gross_salary_target or 0.0
            target_hm = rec.monthly_gross_salary_target_hm or 0.0
            rec.tenenet_residual_hm = max(0.0, target_hm - billed_gross)
            rec.tenenet_residual_ccp = max(0.0, target_ccp - billed_ccp)

    @api.model
    def _normalize_monthly_contributions_to_target(self, contributions, target_ccp, target_hm):
        passthrough_rows = [row for row in contributions if row.get("skip_salary_target_normalization")]
        scalable_rows = [row for row in contributions if not row.get("skip_salary_target_normalization")]
        fixed_rows = [row for row in scalable_rows if row["mode"] == "fixed_ratio"]
        hours_rows = [row for row in scalable_rows if row["mode"] == "hours"]

        def _scaled_rows(rows, scale):
            scaled = []
            for row in rows:
                scaled.append({
                    **row,
                    "hm": (row["hm"] or 0.0) * scale,
                    "ccp": (row["ccp"] or 0.0) * scale,
                })
            return scaled

        normalized = list(passthrough_rows)
        remaining_target_ccp = max(0.0, target_ccp - sum(row["ccp"] for row in normalized))
        remaining_target_hm = max(0.0, target_hm - sum(row["hm"] for row in normalized))
        fixed_total_ccp = sum(row["ccp"] for row in fixed_rows)
        fixed_scale = min(1.0, (remaining_target_ccp / fixed_total_ccp)) if target_ccp > 0.0 and fixed_total_ccp > 0.0 else 1.0
        normalized.extend(_scaled_rows(fixed_rows, fixed_scale))

        remaining_ccp = max(0.0, target_ccp - sum(row["ccp"] for row in normalized))
        hours_total_ccp = sum(row["ccp"] for row in hours_rows)
        hours_scale = min(1.0, (remaining_ccp / hours_total_ccp)) if remaining_ccp > 0.0 and hours_total_ccp > 0.0 else 0.0
        if target_ccp <= 0.0:
            hours_scale = 1.0
        normalized.extend(_scaled_rows(hours_rows, hours_scale))

        if remaining_target_hm > 0.0:
            fixed_total_hm = sum(row["hm"] for row in normalized if row["mode"] == "fixed_ratio" and not row.get("skip_salary_target_normalization"))
            hours_total_hm = sum(row["hm"] for row in normalized if row["mode"] == "hours" and not row.get("skip_salary_target_normalization"))
            total_hm = fixed_total_hm + hours_total_hm
            if total_hm > remaining_target_hm > 0.0:
                hm_scale = remaining_target_hm / total_hm
                normalized = passthrough_rows + _scaled_rows(
                    [row for row in normalized if not row.get("skip_salary_target_normalization")],
                    hm_scale,
                )
        return normalized

    @api.model
    def _get_project_labor_budget_by_month(self, project, period):
        project = project if hasattr(project, "ids") else self.env["tenenet.project"].browse(project)
        normalized_period = fields.Date.to_date(period).replace(day=1)
        budget_lines = project._get_budget_lines_for_year(normalized_period.year, budget_type="labor")
        if not budget_lines:
            return None
        total = 0.0
        for line in budget_lines:
            total += line._get_effective_month_amounts().get(normalized_period.month, 0.0) or 0.0
        return total

    @api.model
    def _get_project_fixed_ratio_contributions(self, project, period):
        project = project if hasattr(project, "ids") else self.env["tenenet.project"].browse(project)
        normalized_period = fields.Date.to_date(period).replace(day=1)
        assignments = project.assignment_ids.filtered(
            lambda assignment: assignment.active
            and assignment.project_id.salary_funding_mode == "fixed_ratio"
            and assignment._is_active_in_period(normalized_period)
            and not assignment.project_id.is_tenenet_internal
        )
        requested_rows = []
        for assignment in assignments:
            requested_ccp = assignment._get_fixed_salary_share(normalized_period)
            requested_hm = assignment._get_fixed_salary_share_hm(normalized_period)
            if requested_ccp <= 0.0 and requested_hm <= 0.0:
                continue
            requested_rows.append({
                "employee_id": assignment.employee_id.id,
                "period": normalized_period,
                "project_id": project.id,
                "project": project,
                "assignment_id": assignment.id,
                "assignment": assignment,
                "mode": "fixed_ratio",
                "hm": requested_hm,
                "ccp": requested_ccp,
                "settlement_only": bool(assignment.settlement_only),
            })

        monthly_budget_ccp = self._get_project_labor_budget_by_month(project, normalized_period)
        if monthly_budget_ccp is None:
            return requested_rows

        total_requested_ccp = sum(row["ccp"] for row in requested_rows)
        if total_requested_ccp <= 0.0:
            return requested_rows

        scale = min(1.0, monthly_budget_ccp / total_requested_ccp) if monthly_budget_ccp > 0.0 else 0.0
        return [
            {
                **row,
                "hm": (row["hm"] or 0.0) * scale,
                "ccp": (row["ccp"] or 0.0) * scale,
            }
            for row in requested_rows
        ]

    @api.model
    def _get_employee_month_project_coverage(self, employee, period):
        employee = employee if hasattr(employee, "ids") else self.env["hr.employee"].browse(employee)
        if not employee:
            return {
                "period": period,
                "contributions": [],
                "hours_hm": 0.0,
                "hours_ccp": 0.0,
                "fixed_ratio_hm": 0.0,
                "fixed_ratio_ccp": 0.0,
                "total_hm": 0.0,
                "total_ccp": 0.0,
            }

        normalized_period = fields.Date.to_date(period).replace(day=1)
        all_assignments = employee.assignment_ids.filtered(
            lambda assignment: assignment.project_id
            and not assignment.project_id.is_tenenet_internal
            and assignment._is_active_in_period(normalized_period)
        )
        contributions = []
        fixed_projects = all_assignments.filtered(
            lambda assignment: assignment.project_id.salary_funding_mode == "fixed_ratio"
        ).mapped("project_id")
        for project in fixed_projects:
            project_rows = self._get_project_fixed_ratio_contributions(project, normalized_period)
            contributions.extend([row for row in project_rows if row["employee_id"] == employee.id])

        for assignment in all_assignments.filtered(lambda assignment: assignment.project_id.salary_funding_mode != "fixed_ratio"):
            mode = assignment.project_id.salary_funding_mode or "hours"
            share = assignment._get_hours_salary_share(normalized_period)
            hm = share["hm"]
            ccp = share["ccp"]
            if hm <= 0.0 and ccp <= 0.0:
                continue
            contributions.append({
                "employee_id": employee.id,
                "period": normalized_period,
                "project_id": assignment.project_id.id,
                "project": assignment.project_id,
                "assignment_id": assignment.id,
                "assignment": assignment,
                "mode": mode,
                "hm": hm,
                "ccp": ccp,
                "settlement_only": bool(assignment.settlement_only),
                "skip_salary_target_normalization": bool(share.get("has_labor_cost_override")),
            })

        target_ccp = employee._get_effective_monthly_gross_salary_target(normalized_period)
        target_hm = employee._get_effective_monthly_gross_salary_target_hm(normalized_period)
        normalized_contributions = contributions
        if target_ccp > 0.0:
            normalized_contributions = self._normalize_monthly_contributions_to_target(
                contributions,
                target_ccp,
                target_hm,
            )
        else:
            normalized_contributions = [row for row in contributions if row["mode"] == "hours"]

        return {
            "period": normalized_period,
            "contributions": normalized_contributions,
            "hours_hm": sum(row["hm"] for row in normalized_contributions if row["mode"] == "hours"),
            "hours_ccp": sum(row["ccp"] for row in normalized_contributions if row["mode"] == "hours"),
            "fixed_ratio_hm": sum(row["hm"] for row in normalized_contributions if row["mode"] == "fixed_ratio"),
            "fixed_ratio_ccp": sum(row["ccp"] for row in normalized_contributions if row["mode"] == "fixed_ratio"),
            "total_hm": sum(row["hm"] for row in normalized_contributions),
            "total_ccp": sum(row["ccp"] for row in normalized_contributions),
        }

    def _get_project_salary_contributions(self):
        self.ensure_one()
        return self._get_employee_month_project_coverage(self.employee_id, self.period)

    def _sync_internal_residual_expense(self):
        InternalExpense = self.env["tenenet.internal.expense"].sudo()
        internal_project = self.env["tenenet.project"].sudo()._ensure_admin_tenenet_entities()
        for rec in self:
            existing = InternalExpense.search([("tenenet_cost_id", "=", rec.id)], limit=1)
            gap_ccp = rec.tenenet_residual_ccp or 0.0
            if gap_ccp <= 0.001:
                if existing:
                    existing.unlink()
                continue

            multiplier = rec.employee_id._get_payroll_contribution_multiplier() if rec.employee_id else self.CCP_MULTIPLIER
            gap_hm = rec.tenenet_residual_hm or (gap_ccp / multiplier)
            hourly_ccp = rec.employee_id.with_context(tenenet_period=rec.period).hourly_rate or 0.0
            vals = {
                "employee_id": rec.employee_id.id,
                "period": rec.period,
                "category": "residual_wage",
                "source_project_id": internal_project.id,
                "tenenet_cost_id": rec.id,
                "cost_hm": gap_hm,
                "wage_hm": hourly_ccp / multiplier if hourly_ccp else 0.0,
                "note": "Nepokrytá časť mesačnej mzdy podľa live projektového krytia. Automaticky presunuté do Admin TENENET.",
            }
            if existing:
                existing.write(vals)
            else:
                InternalExpense.create(vals)

    @api.model
    def _sync_for_employee_period(self, employee_id, period):
        """Create or ensure residual record exists for an employee+period after timesheet changes."""
        employee = self.env["hr.employee"].browse(employee_id).exists()
        if not employee:
            return self.browse()
        normalized_period = fields.Date.to_date(period).replace(day=1)
        coverage = self._get_employee_month_project_coverage(employee, normalized_period)
        existing = self.search([
            ("employee_id", "=", employee_id),
            ("period", "=", normalized_period),
        ], limit=1)
        target_ccp = employee._get_effective_monthly_gross_salary_target(normalized_period)
        target_hm = employee._get_effective_monthly_gross_salary_target_hm(normalized_period)
        has_coverage = bool(coverage["total_ccp"] or coverage["total_hm"])
        if not existing and not has_coverage and target_ccp <= 0.0 and target_hm <= 0.0:
            return self.browse()
        if not existing:
            existing = self.create({
                "employee_id": employee_id,
                "period": normalized_period,
            })
        else:
            existing._compute_period_targets()
            existing._compute_residual()
        existing._sync_internal_residual_expense()
        return existing

    @api.model
    def _sync_for_assignments_periods(self, assignments, periods=None):
        assignments = assignments.filtered(lambda assignment: assignment.employee_id)
        if not assignments:
            return self.browse()
        normalized_periods = {
            fields.Date.to_date(period).replace(day=1)
            for period in (periods or [])
            if period
        }
        for assignment in assignments:
            assignment_periods = normalized_periods or (
                set(assignment._get_expected_periods())
                | set(assignment.timesheet_ids.mapped("period"))
                | set(self.search([("employee_id", "=", assignment.employee_id.id)]).mapped("period"))
            )
            if not assignment_periods:
                assignment_periods = {fields.Date.context_today(self).replace(day=1)}
            for period in assignment_periods:
                self._sync_for_employee_period(assignment.employee_id.id, period)

    @api.model
    def _sync_target_employees_for_year(self, year, employee_ids=None):
        Employee = self.env["hr.employee"].sudo()
        domain = [
            ("active", "=", True),
            ("monthly_gross_salary_target", ">", 0.0),
        ]
        if employee_ids:
            domain.append(("id", "in", list(set(employee_ids))))
        employees = Employee.search(domain)
        for employee in employees:
            for month in range(1, 13):
                self._sync_for_employee_period(employee.id, fields.Date.to_date(f"{year}-{month:02d}-01"))
        return employees

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_internal_residual_expense()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._sync_internal_residual_expense()
        return result
