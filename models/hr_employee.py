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
    education_info = fields.Text(string="Vzdelanie")
    work_hours = fields.Float(
        string="Denný úväzok (hod.)",
        digits=(10, 2),
        default=8.0,
        help="Denný úväzok zamestnanca v hodinách, napr. 8, 6 alebo 4.",
    )
    monthly_capacity_hours = fields.Float(
        string="Mesačný fond hodín",
        digits=(10, 2),
        compute="_compute_workload_from_hours",
        store=True,
        help="Orientačný mesačný fond hodín vypočítaný z denného úväzku. Pri plnom úväzku je to 160 hodín.",
    )
    work_ratio = fields.Float(
        string="Úväzok (%)",
        digits=(5, 2),
        compute="_compute_workload_from_hours",
        store=True,
        help="Percento úväzku vypočítané voči plnému 8-hodinovému úväzku.",
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
    tenenet_cost_ids = fields.One2many(
        "tenenet.employee.tenenet.cost",
        "employee_id",
        string="Tenenet náklady",
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

    @api.model_create_multi
    def create(self, vals_list):
        synced_vals_list = [self._prepare_identity_sync_vals(vals) for vals in vals_list]
        return super().create(synced_vals_list)

    def write(self, vals):
        if len(self) == 1:
            vals = self._prepare_identity_sync_vals(vals, self)
            return super().write(vals)

        for record in self:
            record_vals = record._prepare_identity_sync_vals(vals, record)
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
        self._sync_optional_payroll_cleanup_view()
        return result

    @api.depends("work_hours")
    def _compute_workload_from_hours(self):
        for rec in self:
            hours_per_day = rec.work_hours or 0.0
            ratio = (hours_per_day / 8.0) * 100.0 if hours_per_day > 0 else 0.0
            rec.work_ratio = ratio
            rec.monthly_capacity_hours = 160.0 * ratio / 100.0
