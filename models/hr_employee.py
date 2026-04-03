from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    _PAYROLL_CLEANUP_XMLID = "tenenet_projects.view_hr_employee_form_tenenet_payroll_cleanup_optional"
    _PAYROLL_CLEANUP_ARCH = """
        <data>
            <xpath expr="//button[@icon='fa-dollar']" position="replace"/>
            <xpath expr="//page[@name='salary_attachment']" position="replace"/>
        </data>
    """

    tenenet_number = fields.Integer(string="Interné číslo")
    title_academic = fields.Char(string="Titul")
    first_name = fields.Char(string="Krstné meno", translate=False)
    last_name = fields.Char(string="Priezvisko", translate=False)
    position = fields.Char(string="Pozícia", translate=False)
    position_catalog_id = fields.Many2one(
        "hr.job",
        string="Katalóg pozície",
        ondelete="set null",
    )
    education_info = fields.Text(string="Vzdelanie")
    work_hours = fields.Float(
        string="Denný úväzok (hod.)",
        digits=(10, 2),
        compute="_compute_workload_from_ratio",
        store=True,
        readonly=True,
        help="Denný úväzok odvodený z percenta úväzku pri plnom 8-hodinovom dni.",
    )
    monthly_capacity_hours = fields.Float(
        string="Mesačný fond hodín",
        digits=(10, 2),
        compute="_compute_workload_from_ratio",
        store=True,
        help="Orientačný mesačný fond hodín odvodený z percenta úväzku. Pri plnom úväzku je to 160 hodín.",
    )
    work_ratio = fields.Float(
        string="Úväzok (%)",
        digits=(5, 2),
        default=100.0,
        help="Percento pracovnej kapacity zamestnanca. Pri 100 % je mesačný fond 160 hodín.",
    )
    hourly_rate = fields.Float(string="Hodinová sadzba", digits=(10, 2))
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "employee_id",
        string="Alokácie",
    )
    utilization_ids = fields.One2many(
        "tenenet.utilization",
        "employee_id",
        string="Vyťaženosť",
    )
    pl_line_ids = fields.One2many(
        "tenenet.pl.line",
        "employee_id",
        string="P&L riadky",
    )
    assignment_ids = fields.One2many(
        "tenenet.project.assignment",
        "employee_id",
        string="Priradenia k projektom",
    )
    training_ids = fields.One2many(
        "tenenet.employee.training",
        "employee_id",
        string="Školenia",
    )
    asset_ids = fields.One2many(
        "tenenet.employee.asset",
        "employee_id",
        string="Firemný majetok",
    )
    asset_currency_id = fields.Many2one(
        "res.currency",
        string="Mena majetku",
        default=lambda self: self.env.ref("base.EUR"),
    )
    asset_total_value = fields.Monetary(
        string="Hodnota majetku spolu (€)",
        currency_field="asset_currency_id",
        compute="_compute_asset_total_value",
        store=True,
    )
    site_key_ids = fields.One2many(
        "tenenet.employee.site.key",
        "employee_id",
        string="Kľúče",
    )
    service_ids = fields.One2many(
        "tenenet.employee.service",
        "employee_id",
        string="Služby",
    )
    tenenet_cost_ids = fields.One2many(
        "tenenet.employee.tenenet.cost",
        "employee_id",
        string="Tenenet náklady",
    )
    service_manager_user_ids = fields.Many2many(
        "res.users",
        string="Správcovia služieb",
        relation="hr_employee_service_manager_rel",
        column1="employee_id",
        column2="user_id",
        compute="_compute_service_manager_user_ids",
        store=True,
        recursive=True,
    )
    can_manage_services = fields.Boolean(
        string="Môže spravovať služby",
        compute="_compute_can_manage_services",
    )
    tenenet_allocation_ratio_total = fields.Float(
        string="Projektový úväzok spolu (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_actual_work_ratio = fields.Float(
        string="Skutočný úväzok (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_active_assignment_count = fields.Integer(
        string="Počet aktívnych úväzkov",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_availability_state = fields.Selection(
        [
            ("free", "Voľný"),
            ("partial", "Čiastočne alokovaný"),
            ("full", "Plne alokovaný"),
            ("overbooked", "Preťažený"),
        ],
        string="Stav dostupnosti",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_availability_label = fields.Char(
        string="Dostupnosť",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_free_ratio = fields.Float(
        string="Voľná kapacita (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )

    @api.model
    def _compose_display_name(self, title_academic, first_name, last_name):
        parts = [part.strip() for part in [title_academic, first_name, last_name] if part and part.strip()]
        return " ".join(parts)

    @api.model
    def _compose_legal_name(self, first_name, last_name):
        parts = [part.strip() for part in [first_name, last_name] if part and part.strip()]
        return " ".join(parts)

    @api.model
    def _prepare_identity_sync_vals(self, vals, record=None):
        identity_keys = {"title_academic", "first_name", "last_name"}
        if not identity_keys.intersection(vals):
            return vals

        title_academic = vals.get("title_academic", record.title_academic if record else False)
        first_name = vals.get("first_name", record.first_name if record else False)
        last_name = vals.get("last_name", record.last_name if record else False)

        display_name = self._compose_display_name(title_academic, first_name, last_name)
        legal_name = self._compose_legal_name(first_name, last_name)

        synced_vals = dict(vals)
        if display_name:
            synced_vals["name"] = display_name
        if legal_name:
            synced_vals["legal_name"] = legal_name
        return synced_vals

    @api.model
    def _find_or_create_job_position(self, position_name):
        normalized_name = (position_name or "").strip()
        if not normalized_name:
            return self.env["hr.job"]

        job = self.env["hr.job"].search([("name", "=", normalized_name)], limit=1)
        if not job:
            job = self.env["hr.job"].create({"name": normalized_name})
        return job

    @api.model
    def _prepare_position_sync_vals(self, vals, record=None):
        synced_vals = dict(vals)
        if "position_catalog_id" in vals:
            job = self.env["hr.job"].browse(vals["position_catalog_id"]) if vals["position_catalog_id"] else self.env["hr.job"]
            synced_vals["position"] = job.name or False
            synced_vals["job_id"] = job.id or False
            return synced_vals

        if "job_id" in vals:
            job = self.env["hr.job"].browse(vals["job_id"]) if vals["job_id"] else self.env["hr.job"]
            synced_vals["position"] = job.name or False
            synced_vals["position_catalog_id"] = job.id or False
            return synced_vals

        if "position" not in vals:
            return synced_vals

        job = self._find_or_create_job_position(vals.get("position"))
        synced_vals["position"] = job.name or False
        synced_vals["position_catalog_id"] = job.id or False
        synced_vals["job_id"] = job.id or False
        return synced_vals

    @api.depends("asset_ids", "asset_ids.cost", "asset_ids.active")
    def _compute_asset_total_value(self):
        for employee in self:
            employee.asset_total_value = sum(employee.asset_ids.filtered("active").mapped("cost"))

    @api.model_create_multi
    def create(self, vals_list):
        synced_vals_list = []
        for vals in vals_list:
            synced_vals = self._prepare_identity_sync_vals(vals)
            synced_vals = self._prepare_position_sync_vals(synced_vals)
            synced_vals_list.append(synced_vals)
        return super().create(synced_vals_list)

    def write(self, vals):
        if len(self) == 1:
            vals = self._prepare_identity_sync_vals(vals, self)
            vals = self._prepare_position_sync_vals(vals, self)
            return super().write(vals)

        for record in self:
            record_vals = record._prepare_identity_sync_vals(vals, record)
            record_vals = record._prepare_position_sync_vals(record_vals, record)
            super(HrEmployee, record).write(record_vals)
        return True

    @api.model
    def _sync_optional_payroll_cleanup_view(self):
        payroll_view = self.env.ref("hr_payroll.payroll_hr_employee_view_form", raise_if_not_found=False)
        model_data = self.env["ir.model.data"].sudo()
        existing = model_data.search([
            ("module", "=", "tenenet_projects"),
            ("name", "=", "view_hr_employee_form_tenenet_payroll_cleanup_optional"),
        ], limit=1)

        if not payroll_view:
            if existing and existing.model == "ir.ui.view":
                self.env["ir.ui.view"].sudo().browse(existing.res_id).unlink()
            return

        vals = {
            "name": "hr.employee.form.tenenet.payroll.cleanup.optional",
            "type": "form",
            "model": "hr.employee",
            "inherit_id": payroll_view.id,
            "priority": 260,
            "arch_base": self._PAYROLL_CLEANUP_ARCH,
        }
        view_model = self.env["ir.ui.view"].sudo()
        if existing and existing.model == "ir.ui.view":
            view_model.browse(existing.res_id).write(vals)
            return

        created_view = view_model.create(vals)
        model_data.create({
            "module": "tenenet_projects",
            "name": "view_hr_employee_form_tenenet_payroll_cleanup_optional",
            "model": "ir.ui.view",
            "res_id": created_view.id,
            "noupdate": True,
        })

    def _register_hook(self):
        result = super()._register_hook()
        try:
            with self.env.cr.savepoint():
                self._sync_optional_payroll_cleanup_view()
        except Exception:
            # Another worker already updated the view; safe to skip.
            pass
        return result

    @api.depends("work_ratio")
    def _compute_workload_from_ratio(self):
        for rec in self:
            ratio = rec.work_ratio or 0.0
            hours_per_day = 8.0 * ratio / 100.0
            rec.work_hours = hours_per_day
            rec.monthly_capacity_hours = 160.0 * ratio / 100.0

    @api.depends("parent_id", "parent_id.user_id", "parent_id.service_manager_user_ids")
    def _compute_service_manager_user_ids(self):
        for rec in self:
            manager_users = self.env["res.users"]
            if rec.parent_id:
                manager_users |= rec.parent_id.user_id
                manager_users |= rec.parent_id.service_manager_user_ids
            rec.service_manager_user_ids = manager_users

    def _compute_can_manage_services(self):
        current_user = self.env.user
        is_hr_manager = current_user.has_group("hr.group_hr_manager")
        for rec in self:
            rec.can_manage_services = bool(
                is_hr_manager
                or rec.service_manager_user_ids.filtered(lambda user: user == current_user)
            )

    @api.depends(
        "work_ratio",
        "assignment_ids.active",
        "assignment_ids.allocation_ratio",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.is_current",
        "assignment_ids.project_id.date_start",
        "assignment_ids.project_id.date_end",
    )
    def _compute_tenenet_assignment_availability(self):
        for rec in self:
            active_assignments = rec.assignment_ids.filtered(lambda assignment: assignment.is_current)
            capacity_ratio = rec.work_ratio or 0.0
            total_ratio = sum(active_assignments.mapped("allocation_ratio"))
            rec.tenenet_allocation_ratio_total = total_ratio
            rec.tenenet_actual_work_ratio = total_ratio
            rec.tenenet_active_assignment_count = len(active_assignments)
            rec.tenenet_free_ratio = max(0.0, capacity_ratio - total_ratio)
            if total_ratio <= 0.0:
                rec.tenenet_availability_state = "free"
                rec.tenenet_availability_label = "Voľný"
            elif capacity_ratio > 0.0 and total_ratio < capacity_ratio:
                rec.tenenet_availability_state = "partial"
                rec.tenenet_availability_label = "Čiastočne alokovaný"
            elif total_ratio == capacity_ratio:
                rec.tenenet_availability_state = "full"
                rec.tenenet_availability_label = "Plne alokovaný"
            else:
                rec.tenenet_availability_state = "overbooked"
                rec.tenenet_availability_label = "Preťažený"
