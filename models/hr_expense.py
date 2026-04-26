from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    tenenet_cost_flow = fields.Selection(
        [
            ("project", "Projektový náklad"),
            ("operating", "Prevádzkový náklad"),
        ],
        string="TENENET tok nákladu",
        default="project",
        required=True,
        tracking=True,
    )
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
    tenenet_available_expense_type_config_ids = fields.Many2many(
        "tenenet.expense.type.config",
        compute="_compute_tenenet_available_expense_type_config_ids",
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
    tenenet_type_supported_on_project = fields.Boolean(
        string="Typ je povolený na projekte",
        compute="_compute_tenenet_allowed_type_shortcut",
    )
    tenenet_can_add_allowed_type = fields.Boolean(
        string="Môže pridať povolený typ",
        compute="_compute_tenenet_allowed_type_shortcut",
    )
    tenenet_add_allowed_type = fields.Boolean(
        string="Pridať medzi povolené výdavky projektu",
        default=False,
        copy=False,
    )
    tenenet_allowed_type_limit = fields.Monetary(
        string="Limit pre projekt",
        currency_field="company_currency_id",
        default=0.0,
        copy=False,
        help="Celkový limit tohto typu výdavku na projekte. 0 = bez limitu.",
    )
    tenenet_import_source_key = fields.Char(
        string="TENENET import source key",
        copy=False,
        index=True,
    )

    @api.depends("employee_id", "date")
    def _compute_tenenet_available_project_ids(self):
        for rec in self:
            rec.tenenet_available_project_ids = rec._get_tenenet_available_projects()

    @api.depends("tenenet_cost_flow")
    def _compute_tenenet_available_expense_type_config_ids(self):
        Config = self.env["tenenet.expense.type.config"].with_context(active_test=False)
        configs = Config.search([("active", "=", True)])
        for rec in self:
            allowed_usage = ["project", "both"] if rec.tenenet_cost_flow != "operating" else ["operating", "both"]
            rec.tenenet_available_expense_type_config_ids = configs.filtered(
                lambda cfg: cfg.tenenet_usage in allowed_usage
            )

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

    @api.depends("tenenet_project_id", "tenenet_expense_type_config_id")
    def _compute_tenenet_allowed_type_shortcut(self):
        can_add_allowed_type = self.env["tenenet.project.allowed.expense.type"].browse().has_access("create")
        for rec in self:
            rec.tenenet_can_add_allowed_type = bool(can_add_allowed_type) and rec.tenenet_cost_flow == "project"
            rec.tenenet_type_supported_on_project = (
                rec.tenenet_cost_flow == "project" and bool(rec._get_tenenet_matching_allowed_type())
            )

    @api.onchange("employee_id", "date")
    def _onchange_tenenet_employee_or_date(self):
        for rec in self:
            available_projects = rec._get_tenenet_available_projects()
            if rec.tenenet_project_id and rec.tenenet_project_id not in available_projects:
                rec.tenenet_project_id = False

    @api.onchange("tenenet_cost_flow")
    def _onchange_tenenet_cost_flow(self):
        for rec in self:
            if rec.tenenet_cost_flow == "operating":
                rec.tenenet_project_id = False
            rec.tenenet_add_allowed_type = False
            rec.tenenet_allowed_type_limit = 0.0

    @api.onchange("tenenet_expense_type_config_id")
    def _onchange_tenenet_expense_type_config_id(self):
        for rec in self:
            rec._apply_tenenet_category_from_config()
            rec.tenenet_add_allowed_type = False
            rec.tenenet_allowed_type_limit = 0.0

    @api.onchange("tenenet_project_id")
    def _onchange_tenenet_project_id(self):
        for rec in self:
            if rec.tenenet_project_id:
                rec.tenenet_cost_flow = "project"
            rec.tenenet_add_allowed_type = False
            rec.tenenet_allowed_type_limit = 0.0

    @api.constrains("tenenet_project_id", "tenenet_expense_type_config_id", "tenenet_cost_flow")
    def _check_tenenet_type_required(self):
        for rec in self:
            if rec.tenenet_cost_flow == "operating" and not rec.tenenet_expense_type_config_id:
                raise ValidationError(_("Pre TENENET prevádzkový náklad musíte vybrať typ výdavku."))
            if rec.tenenet_project_id and not rec.tenenet_expense_type_config_id:
                raise ValidationError(_("Pre TENENET projektový výdavok musíte vybrať typ výdavku."))
            config = rec.tenenet_expense_type_config_id
            if not config:
                continue
            if rec.tenenet_cost_flow == "operating" and config.tenenet_usage not in {"operating", "both"}:
                raise ValidationError(_("Vybraný typ výdavku nie je povolený pre prevádzkové náklady."))
            if rec.tenenet_cost_flow == "project" and config.tenenet_usage not in {"project", "both"}:
                raise ValidationError(_("Vybraný typ výdavku nie je povolený pre projektové náklady."))

    @api.constrains("tenenet_project_id", "employee_id", "date")
    def _check_tenenet_project_access(self):
        for rec in self.filtered("tenenet_project_id"):
            if rec.tenenet_import_source_key:
                continue
            if rec.tenenet_project_id not in rec._get_tenenet_available_projects():
                raise ValidationError(
                    _("Na tomto výdavku je možné vybrať len projekty priradené zamestnancovi alebo projekty, kde je garant/PM.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        allow_type_requests = []
        prepared_vals_list = []
        for vals in vals_list:
            vals, allow_type_request = self._pop_tenenet_allowed_type_request(vals)
            allow_type_requests.append(allow_type_request)
            prepared_vals_list.append(self._prepare_tenenet_category_vals(vals))

        vals_list = prepared_vals_list
        records = super().create(vals_list)
        for rec, allow_type_request in zip(records, allow_type_requests):
            rec._ensure_tenenet_allowed_type(allow_type_request)
        records._sync_tenenet_project_expenses()
        return records

    def write(self, vals):
        vals, allow_type_request = self._pop_tenenet_allowed_type_request(vals)
        if "tenenet_expense_type_config_id" in vals or "product_id" in vals:
            if len(self) == 1:
                vals = self._prepare_tenenet_category_vals(vals, self)
            else:
                for rec in self:
                    super(HrExpense, rec).write(self._prepare_tenenet_category_vals(vals, rec))
                    rec._ensure_tenenet_allowed_type(allow_type_request)
                    rec._sync_tenenet_project_expenses()
                return True
        result = super().write(vals)
        self._ensure_tenenet_allowed_type(allow_type_request)
        self._sync_tenenet_project_expenses()
        return result

    def _pop_tenenet_allowed_type_request(self, vals):
        cleaned_vals = dict(vals)
        allow_create = bool(cleaned_vals.pop("tenenet_add_allowed_type", False))
        limit = cleaned_vals.pop("tenenet_allowed_type_limit", 0.0)
        return cleaned_vals, {
            "create": allow_create,
            "max_amount": limit or 0.0,
        }

    def _prepare_tenenet_category_vals(self, vals, record=None):
        prepared_vals = dict(vals)
        cost_flow = prepared_vals.get(
            "tenenet_cost_flow",
            record.tenenet_cost_flow if record else "project",
        )
        if cost_flow == "operating":
            prepared_vals["tenenet_project_id"] = False
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
        if self.tenenet_cost_flow != "project" or not project or not config:
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
        if not self.tenenet_expense_type_config_id:
            return zero
        if self.tenenet_cost_flow == "operating":
            return {
                "allowed_type": self.env["tenenet.project.allowed.expense.type"],
                "project_amount": 0.0,
                "internal_amount": self.total_amount or 0.0,
                "note": _("Prevádzkový náklad ide celý do interných nákladov."),
            }
        if not self.tenenet_project_id:
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

    def _ensure_tenenet_allowed_type(self, allow_type_request):
        request = allow_type_request or {}
        if not request.get("create"):
            return

        AllowedType = self.env["tenenet.project.allowed.expense.type"]
        AllowedType.browse().check_access("create")
        for rec in self:
            if rec.tenenet_cost_flow != "project" or not rec.tenenet_project_id or not rec.tenenet_expense_type_config_id:
                continue
            if rec._get_tenenet_matching_allowed_type():
                continue

            config = rec.tenenet_expense_type_config_id
            AllowedType.create({
                "project_id": rec.tenenet_project_id.id,
                "config_id": config.id,
                "name": config.name,
                "description": config.description or False,
                "max_amount": request.get("max_amount", 0.0),
            })

    def _sync_tenenet_project_expenses(self):
        ProjectExpense = self.env["tenenet.project.expense"].sudo()
        InternalExpense = self.env["tenenet.internal.expense"].sudo()

        for rec in self:
            project_expense = ProjectExpense.search([("hr_expense_id", "=", rec.id)], limit=1)
            internal_expense = InternalExpense.search([("hr_expense_id", "=", rec.id)], limit=1)

            if not rec.tenenet_expense_type_config_id:
                project_expense.unlink()
                internal_expense.unlink()
                continue

            split = rec._get_tenenet_split_values()
            allowed_type = split["allowed_type"]
            description = rec.name or rec.product_id.display_name or _("Výdavok")
            expense_date = rec.date or fields.Date.context_today(rec)
            period = expense_date.replace(day=1)

            if rec.tenenet_cost_flow == "project" and split["project_amount"] > 0.0 and allowed_type:
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
                    "source_project_id": rec.tenenet_project_id.id if rec.tenenet_cost_flow == "project" else False,
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
