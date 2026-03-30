from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    tenenet_project_id = fields.Many2one(
        "tenenet.project",
        string="TENENET projekt",
        readonly=False,
    )
    tenenet_available_project_ids = fields.Many2many(
        "tenenet.project",
        compute="_compute_tenenet_available_project_ids",
    )
    tenenet_expense_type_config_id = fields.Many2one(
        "tenenet.expense.type.config",
        string="TENENET typ výdavku",
        domain=[("active", "=", True)],
        readonly=False,
    )
    tenenet_allowed_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_tenenet_allowed_product_ids",
    )
    tenenet_allowed_type_id = fields.Many2one(
        "tenenet.project.allowed.expense.type",
        string="Povolený typ projektu",
        compute="_compute_tenenet_split",
    )
    tenenet_project_amount = fields.Monetary(
        string="Projektové náklady",
        currency_field="company_currency_id",
        compute="_compute_tenenet_split",
    )
    tenenet_internal_amount = fields.Monetary(
        string="Interné náklady",
        currency_field="company_currency_id",
        compute="_compute_tenenet_split",
    )
    tenenet_split_note = fields.Char(
        string="Rozúčtovanie TENENET",
        compute="_compute_tenenet_split",
    )
    tenenet_project_expense_ids = fields.One2many(
        "tenenet.project.expense",
        "hr_expense_id",
        string="TENENET projektové výdavky",
    )
    tenenet_internal_expense_ids = fields.One2many(
        "tenenet.internal.expense",
        "hr_expense_id",
        string="TENENET interné výdavky",
    )

    @api.depends("employee_id", "date")
    def _compute_tenenet_available_project_ids(self):
        for rec in self:
            rec.tenenet_available_project_ids = rec._get_tenenet_available_projects()

    @api.depends("tenenet_expense_type_config_id", "tenenet_expense_type_config_id.expense_category_line_ids.product_id")
    def _compute_tenenet_allowed_product_ids(self):
        for rec in self:
            rec.tenenet_allowed_product_ids = rec.tenenet_expense_type_config_id.expense_category_line_ids.mapped("product_id")

    @api.depends(
        "tenenet_project_id",
        "tenenet_expense_type_config_id",
        "total_amount",
        "employee_id",
        "date",
    )
    def _compute_tenenet_split(self):
        for rec in self:
            split = rec._get_tenenet_split_values()
            rec.tenenet_allowed_type_id = split["allowed_type"]
            rec.tenenet_project_amount = split["project_amount"]
            rec.tenenet_internal_amount = split["internal_amount"]
            rec.tenenet_split_note = split["note"]

    @api.onchange("employee_id", "date")
    def _onchange_tenenet_employee_or_date(self):
        for rec in self:
            available_projects = rec._get_tenenet_available_projects()
            if rec.tenenet_project_id and rec.tenenet_project_id not in available_projects:
                rec.tenenet_project_id = False

    @api.onchange("tenenet_expense_type_config_id")
    def _onchange_tenenet_expense_type_config_id(self):
        for rec in self:
            rec._apply_tenenet_category_from_config()

    @api.constrains("tenenet_project_id", "tenenet_expense_type_config_id")
    def _check_tenenet_type_required(self):
        for rec in self:
            if rec.tenenet_project_id and not rec.tenenet_expense_type_config_id:
                raise ValidationError(_("Pre TENENET projektový výdavok musíte vybrať typ výdavku."))

    @api.constrains("tenenet_project_id", "employee_id", "date")
    def _check_tenenet_project_access(self):
        for rec in self.filtered("tenenet_project_id"):
            if rec.tenenet_project_id not in rec._get_tenenet_available_projects():
                raise ValidationError(
                    _("Na tomto výdavku je možné vybrať len projekty priradené zamestnancovi alebo projekty, kde je garant/PM.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_tenenet_category_vals(vals) for vals in vals_list]
        records = super().create(vals_list)
        records._sync_tenenet_project_expenses()
        return records

    def write(self, vals):
        if "tenenet_expense_type_config_id" in vals or "product_id" in vals:
            if len(self) == 1:
                vals = self._prepare_tenenet_category_vals(vals, self)
            else:
                for rec in self:
                    super(HrExpense, rec).write(self._prepare_tenenet_category_vals(vals, rec))
                    rec._sync_tenenet_project_expenses()
                return True
        result = super().write(vals)
        self._sync_tenenet_project_expenses()
        return result

    def _prepare_tenenet_category_vals(self, vals, record=None):
        prepared_vals = dict(vals)
        config_id = prepared_vals.get(
            "tenenet_expense_type_config_id",
            record.tenenet_expense_type_config_id.id if record else False,
        )
        if not config_id:
            return prepared_vals

        config = self.env["tenenet.expense.type.config"].browse(config_id)
        allowed_products = config.expense_category_line_ids.mapped("product_id")
        if not allowed_products:
            return prepared_vals

        product_id = prepared_vals.get("product_id", record.product_id.id if record else False)
        if product_id and product_id in allowed_products.ids:
            return prepared_vals

        prepared_vals["product_id"] = config._get_primary_expense_category().id
        return prepared_vals

    def _apply_tenenet_category_from_config(self):
        self.ensure_one()
        config = self.tenenet_expense_type_config_id
        if not config:
            return

        allowed_products = config.expense_category_line_ids.mapped("product_id")
        if not allowed_products:
            return

        if self.product_id in allowed_products:
            return

        self.product_id = config._get_primary_expense_category()

    def _get_tenenet_available_projects(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return self.env["tenenet.project"]

        expense_date = self.date or fields.Date.context_today(self)
        period_start = expense_date.replace(day=1)

        assignments = self.env["tenenet.project.assignment"].search([
            ("employee_id", "=", employee.id),
            ("active", "=", True),
            ("project_id.active", "=", True),
        ])
        assignment_projects = assignments.filtered(
            lambda assignment: assignment._is_period_in_scope(period_start)
        ).mapped("project_id")

        manager_projects = self.env["tenenet.project"].search([
            ("active", "=", True),
            "|",
            ("odborny_garant_id", "=", employee.id),
            ("project_manager_id", "=", employee.id),
        ])

        return assignment_projects | manager_projects | self.tenenet_project_id

    def _get_tenenet_matching_allowed_type(self):
        self.ensure_one()
        project = self.tenenet_project_id
        config = self.tenenet_expense_type_config_id
        if not project or not config:
            return self.env["tenenet.project.allowed.expense.type"]

        allowed_type = project.allowed_expense_type_ids.filtered(
            lambda line: line.config_id == config
        )[:1]
        if allowed_type:
            return allowed_type
        return project.allowed_expense_type_ids.filtered(
            lambda line: not line.config_id and line.name == config.name
        )[:1]

    def _get_tenenet_split_values(self):
        self.ensure_one()
        zero = {
            "allowed_type": self.env["tenenet.project.allowed.expense.type"],
            "project_amount": 0.0,
            "internal_amount": 0.0,
            "note": False,
        }
        if not self.tenenet_project_id or not self.tenenet_expense_type_config_id:
            return zero

        amount = self.total_amount or 0.0
        allowed_type = self._get_tenenet_matching_allowed_type()
        if not allowed_type:
            return {
                "allowed_type": self.env["tenenet.project.allowed.expense.type"],
                "project_amount": 0.0,
                "internal_amount": amount,
                "note": _("Typ výdavku nie je na projekte povolený, preto ide celý interne."),
            }

        if not allowed_type.max_amount:
            return {
                "allowed_type": allowed_type,
                "project_amount": amount,
                "internal_amount": 0.0,
                "note": _("Typ výdavku je povolený bez limitu."),
            }

        domain = [
            ("allowed_type_id", "=", allowed_type.id),
            ("charged_to", "=", "project"),
        ]
        if self.id:
            domain.append(("hr_expense_id", "!=", self.id))
        already_spent = sum(
            self.env["tenenet.project.expense"].search(domain).mapped("amount")
        )
        remaining = max(0.0, allowed_type.max_amount - already_spent)
        project_amount = min(amount, remaining)
        internal_amount = max(0.0, amount - project_amount)

        if internal_amount:
            note = _("Typ je povolený, ale limit projektu nestačí na celú sumu.")
        else:
            note = _("Typ je povolený a celý výdavok sa pokryje z projektu.")
        return {
            "allowed_type": allowed_type,
            "project_amount": project_amount,
            "internal_amount": internal_amount,
            "note": note,
        }

    def _sync_tenenet_project_expenses(self):
        ProjectExpense = self.env["tenenet.project.expense"].sudo()
        InternalExpense = self.env["tenenet.internal.expense"].sudo()

        for rec in self:
            project_expense = ProjectExpense.search([("hr_expense_id", "=", rec.id)], limit=1)
            internal_expense = InternalExpense.search([("hr_expense_id", "=", rec.id)], limit=1)

            if not rec.tenenet_project_id or not rec.tenenet_expense_type_config_id:
                project_expense.unlink()
                internal_expense.unlink()
                continue

            split = rec._get_tenenet_split_values()
            allowed_type = split["allowed_type"]
            description = rec.name or rec.product_id.display_name or _("Výdavok")
            expense_date = rec.date or fields.Date.context_today(rec)
            period = expense_date.replace(day=1)

            if split["project_amount"] > 0.0 and allowed_type:
                project_vals = {
                    "project_id": rec.tenenet_project_id.id,
                    "allowed_type_id": allowed_type.id,
                    "expense_type_config_id": rec.tenenet_expense_type_config_id.id,
                    "hr_expense_id": rec.id,
                    "date": expense_date,
                    "amount": split["project_amount"],
                    "description": description,
                    "note": _("Synchronizované z HR výdavku %s.") % rec.id,
                    "charged_to": "project",
                }
                if project_expense:
                    project_expense.write(project_vals)
                else:
                    ProjectExpense.create(project_vals)
            else:
                project_expense.unlink()

            if split["internal_amount"] > 0.0:
                internal_vals = {
                    "employee_id": rec.employee_id.id,
                    "period": period,
                    "category": "expense",
                    "hr_expense_id": rec.id,
                    "source_project_id": rec.tenenet_project_id.id,
                    "expense_type_config_id": rec.tenenet_expense_type_config_id.id,
                    "expense_amount": split["internal_amount"],
                    "note": split["note"],
                }
                if internal_expense:
                    internal_expense.write(internal_vals)
                else:
                    InternalExpense.create(internal_vals)
            else:
                internal_expense.unlink()
