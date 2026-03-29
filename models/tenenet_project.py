import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class TenenetProject(models.Model):
    _name = "tenenet.project"
    _description = "Projekt TENENET"
    _order = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Názov projektu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    is_tenenet_internal = fields.Boolean(
        string="Interný TENENET projekt",
        default=False,
        help="Interný projekt pre náklady absencií, ktoré nie sú pokryté projektovými pravidlami.",
    )
    contract_number = fields.Char(string="Číslo zmluvy")
    duration = fields.Integer(string="Trvanie (mesiace)", compute="_compute_duration", store=True)
    recipient_name = fields.Char(string="Príjemca", related="recipient_partner_id.name", store=True, readonly=True, translate=False)
    recipient_partner_id = fields.Many2one(
        "res.partner",
        string="Príjemca",
        ondelete="set null",
        default=lambda self: self.env["res.partner"].search([("name", "=", "TENENET o.z.")], limit=1),
    )
    date_contract = fields.Date(string="Dátum podpisania zmluvy")
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")
    partner_id = fields.Many2one("res.partner", string="Partner", ondelete="restrict")
    partners = fields.Char(string="Partneri", related="partner_id.name", store=True, readonly=True)
    portal = fields.Char(string="Portál")

    semaphore = fields.Selection(
        [("green", "Zelená"), ("yellow", "Žltá"), ("red", "Červená")],
        string="Semafor",
    )

    program_ids = fields.Many2many(
        "tenenet.program",
        "tenenet_project_program_rel",
        "project_id",
        "program_id",
        string="Programy",
    )
    donor_id = fields.Many2one("tenenet.donor", string="Donor", ondelete="restrict")

    odborny_garant_id = fields.Many2one("hr.employee", string="Odborný garant")
    project_manager_id = fields.Many2one("hr.employee", string="Projektový manažér")
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "project_id",
        string="Alokácie (archiv)",
    )
    assignment_ids = fields.One2many(
        "tenenet.project.assignment",
        "project_id",
        string="Priradenia zamestnancov",
    )
    leave_rule_ids = fields.One2many(
        "tenenet.project.leave.rule",
        "project_id",
        string="Pravidlá dovolenky",
    )
    timesheet_ids = fields.One2many(
        "tenenet.project.timesheet",
        "project_id",
        string="Timesheety",
    )
    receipt_line_ids = fields.One2many(
        "tenenet.project.receipt",
        "project_id",
        string="Prijaté podľa rokov",
    )
    milestone_ids = fields.One2many(
        "tenenet.project.milestone",
        "project_id",
        string="Míľniky",
    )
    can_manage_milestones = fields.Boolean(
        string="Môže spravovať míľniky",
        compute="_compute_can_manage_milestones",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    budget_total = fields.Monetary(
        string="Prijaté spolu (€)",
        currency_field="currency_id",
        compute="_compute_budget_total",
        store=True,
    )
    kanban_color = fields.Integer(
        string="Farba kanban",
        compute="_compute_kanban_color",
        store=True,
    )
    default_max_monthly_wage_hm = fields.Float(
        string="Max. mesačná mzda HM (predvolená)",
        digits=(10, 4),
        default=0.0,
        help="Predvolený mesačný strop hrubej mzdy pre priradenia na tomto projekte. 0 = bez stropu.",
    )
    default_max_monthly_wage_ccp = fields.Float(
        string="Max. mesačná sadzba CCP (predvolená)",
        digits=(10, 4),
        compute="_compute_default_max_monthly_wage_ccp",
        store=True,
        help="Predvolený mesačný strop CCP = max. mzda HM × 1.362",
    )
    comments = fields.Text(string="Komentáre")
    donor_contact = fields.Text(string="Kontakt donor", compute="_compute_donor_contact", store=True)
    partner_contact = fields.Text(string="Kontakt partner", compute="_compute_partner_contact", store=True)
    allowed_expense_type_ids = fields.One2many(
        "tenenet.project.allowed.expense.type",
        "project_id",
        string="Povolené typy výdavkov",
    )
    expense_ids = fields.One2many(
        "tenenet.project.expense",
        "project_id",
        string="Výdavky projektu",
    )
    active_year_from = fields.Integer(
        string="Rok od",
        compute="_compute_active_year_range",
        store=True,
    )
    active_year_to = fields.Integer(
        string="Rok do",
        compute="_compute_active_year_range",
        store=True,
    )

    @api.depends("date_start", "date_end")
    def _compute_active_year_range(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.active_year_from = min(rec.date_start.year, rec.date_end.year)
                rec.active_year_to = max(rec.date_start.year, rec.date_end.year)
            elif rec.date_start:
                rec.active_year_from = rec.date_start.year
                rec.active_year_to = rec.date_start.year
            elif rec.date_end:
                rec.active_year_from = rec.date_end.year
                rec.active_year_to = rec.date_end.year
            else:
                rec.active_year_from = False
                rec.active_year_to = False

    CCP_MULTIPLIER = 1.362

    @api.depends("default_max_monthly_wage_hm")
    def _compute_default_max_monthly_wage_ccp(self):
        for rec in self:
            rec.default_max_monthly_wage_ccp = (rec.default_max_monthly_wage_hm or 0.0) * self.CCP_MULTIPLIER

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                start_date = min(rec.date_start, rec.date_end)
                end_date = max(rec.date_start, rec.date_end)
                rec.duration = ((end_date.year - start_date.year) * 12) + (
                    end_date.month - start_date.month
                ) + 1
            elif rec.date_start and not rec.date_end:
                current_date = fields.Date.today()
                rec.duration = (current_date.year - rec.date_start.year) * 12 + (
                    current_date.month - rec.date_start.month
                ) + 1
            else:
                rec.duration = False

    @api.depends("donor_id.contact_info")
    def _compute_donor_contact(self):
        for rec in self:
            rec.donor_contact = rec.donor_id.contact_info or False

    @api.depends(
        "partner_id",
        "partner_id.name",
        "partner_id.email",
        "partner_id.phone",
        "partner_id.street",
        "partner_id.street2",
        "partner_id.zip",
        "partner_id.city",
        "partner_id.country_id.name",
        "partner_id.website",
    )
    def _compute_partner_contact(self):
        for rec in self:
            rec.partner_contact = rec._format_partner_contact(rec.partner_id)

    @api.depends("receipt_line_ids", "receipt_line_ids.amount")
    def _compute_budget_total(self):
        for rec in self:
            rec.budget_total = sum(rec.receipt_line_ids.mapped("amount"))

    @api.depends("semaphore")
    def _compute_kanban_color(self):
        color_map = {"green": 10, "yellow": 3, "red": 1}
        for rec in self:
            rec.kanban_color = color_map.get(rec.semaphore, 0)

    @api.depends("odborny_garant_id", "odborny_garant_id.user_id")
    def _compute_can_manage_milestones(self):
        current_user = self.env.user
        is_manager = current_user.has_group("tenenet_projects.group_tenenet_manager")
        employee_ids = set(current_user.employee_ids.ids)
        for rec in self:
            rec.can_manage_milestones = bool(
                is_manager
                or (rec.odborny_garant_id.id and rec.odborny_garant_id.id in employee_ids)
            )

    def _sync_garant_pm_group(self):
        group = self.env.ref("tenenet_projects.group_tenenet_garant_pm", raise_if_not_found=False)
        group_manager = self.env.ref("tenenet_projects.group_tenenet_manager", raise_if_not_found=False)
        if not group:
            return
        affected = self.mapped("odborny_garant_id") | self.mapped("project_manager_id")
        for employee in affected:
            user = employee.user_id
            if not user:
                continue
            # Managers already have broader access — leave their groups untouched
            if group_manager and group_manager in user.group_ids:
                continue
            still_qualifies = bool(self.env["tenenet.project"].search_count([
                ("active", "=", True),
                "|",
                ("odborny_garant_id", "=", employee.id),
                ("project_manager_id", "=", employee.id),
            ]))
            in_group = group in user.group_ids
            if still_qualifies and not in_group:
                user.write({"group_ids": [(4, group.id)]})
            elif not still_qualifies and in_group:
                user.write({"group_ids": [(3, group.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_garant_pm_group()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "date_start" in vals or "date_end" in vals:
            self.mapped("assignment_ids")._sync_precreated_timesheets()
        if "odborny_garant_id" in vals or "project_manager_id" in vals or "active" in vals:
            self._sync_garant_pm_group()
        return result

    @api.model
    def action_open_garant_projects(self):
        if self.env.user.has_group("tenenet_projects.group_tenenet_manager"):
            domain = [("active", "=", True)]
        else:
            domain = [
                ("active", "=", True), "|",
                ("odborny_garant_id.user_id", "=", self.env.uid),
                ("project_manager_id.user_id", "=", self.env.uid),
            ]
        return {
            "name": "Moje projekty (Garant/PM)",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project",
            "view_mode": "kanban,list",
            "domain": domain,
            "views": [
                (self.env.ref("tenenet_projects.view_tenenet_project_garant_kanban").id, "kanban"),
                (False, "list"),
            ],
        }

    def action_open_cashflow_gantt(self):
        self.ensure_one()
        context = {"default_project_id": self.id}
        if self.receipt_line_ids:
            # Open to the year of the most recent receipt for convenience
            context["cashflow_initial_year"] = max(self.receipt_line_ids.mapped("year"))
        return {
            "type": "ir.actions.act_window",
            "name": "Predikovaný cashflow",
            "res_model": "tenenet.project.cashflow",
            "view_mode": "gantt",
            "domain": [("project_id", "=", self.id)],
            "context": context,
            "target": "current",
        }

    def action_open_receipt_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať príjem projektu",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.receipt.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_assignment_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať priradenie zamestnanca",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.assignment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_allowed_expense_type_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať povolený typ výdavku",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.allowed.expense.type.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_milestone_wizard(self):
        self.ensure_one()
        self._check_milestone_manage_access()
        return {
            "name": "Pridať míľnik",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.milestone.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_assignments_kanban(self):
        self.ensure_one()
        return {
            "name": self.name,
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.assignment",
            "view_mode": "kanban,list",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id, "search_default_active": 1},
        }

    def action_open_timesheet_month_matrix(self):
        self.ensure_one()
        self.assignment_ids._sync_precreated_timesheets()
        action = self.env.ref("tenenet_projects.action_tenenet_project_timesheet_matrix").read()[0]
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "search_default_group_employee": 1,
            "search_default_group_year": 1,
        }
        return action

    @api.model
    def _format_partner_contact(self, partner):
        if not partner:
            return False

        lines = []
        if partner.name:
            lines.append(partner.name)
        if partner.email:
            lines.append(partner.email)

        phones = [value for value in [partner.phone] if value]
        if phones:
            lines.append(" / ".join(dict.fromkeys(phones)))

        address_parts = [value for value in [partner.street, partner.street2] if value]
        city_line = " ".join(value for value in [partner.zip, partner.city] if value)
        if city_line:
            address_parts.append(city_line)
        if partner.country_id:
            address_parts.append(partner.country_id.name)
        if address_parts:
            lines.append(", ".join(address_parts))

        if partner.website:
            lines.append(partner.website)

        return "\n".join(lines) if lines else False

    def _check_milestone_manage_access(self):
        current_user = self.env.user
        is_manager = current_user.has_group("tenenet_projects.group_tenenet_manager")
        employee_ids = set(current_user.employee_ids.ids)
        for rec in self:
            is_garant = rec.odborny_garant_id.id in employee_ids
            if not (is_manager or is_garant):
                raise AccessError(
                    _("Míľniky môže upravovať iba TENENET manažér alebo odborný garant projektu.")
                )

    @api.constrains("is_tenenet_internal", "active")
    def _check_single_active_internal_project(self):
        for rec in self:
            if not rec.is_tenenet_internal or not rec.active:
                continue
            duplicate_count = self.search_count([
                ("id", "!=", rec.id),
                ("is_tenenet_internal", "=", True),
                ("active", "=", True),
            ])
            if duplicate_count:
                raise ValidationError(
                    "Môže existovať iba jeden aktívny interný TENENET projekt."
                )

    @api.model
    def _get_or_create_internal_project(self):
        _logger.warning(
            "DEPRECATED: _get_or_create_internal_project is deprecated. "
            "Use tenenet.internal.expense instead of the internal project mechanism."
        )
        project = self.with_context(active_test=False).search([
            ("is_tenenet_internal", "=", True),
            ("active", "=", True),
        ], limit=1)
        if project:
            return project

        project = self.with_context(active_test=False).search([
            ("is_tenenet_internal", "=", True),
        ], limit=1)
        if project:
            if not project.active:
                project.active = True
            return project

        return self.create({
            "name": "TENENET interné náklady",
            "is_tenenet_internal": True,
            "active": True,
        })
