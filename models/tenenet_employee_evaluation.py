from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TenenetEmployeeEvaluation(models.Model):
    _name = "tenenet.employee.evaluation"
    _description = "Ročné hodnotenie zamestnanca"
    _order = "year desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        index=True,
    )
    year = fields.Integer(
        string="Rok",
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    year_display = fields.Char(
        string="Rok",
        compute="_compute_year_display",
        inverse="_inverse_year_display",
    )
    manager_id = fields.Many2one(
        "hr.employee",
        string="Nadriadený",
        ondelete="set null",
    )
    manager_name = fields.Char(
        string="Meno nadriadeného",
        related="manager_id.name",
        readonly=True,
        store=True,
    )
    author_user_id = fields.Many2one(
        "res.users",
        string="Autor",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    summary = fields.Text(string="Celkové zhodnotenie")
    strengths = fields.Text(string="Silné stránky")
    goals = fields.Text(string="Ciele na ďalší rok")
    recommendations = fields.Text(string="Odporúčania")
    visible_to_employee = fields.Boolean(
        string="Viditeľné zamestnancovi",
        default=True,
    )
    active = fields.Boolean(string="Aktívne", default=True)
    display_name = fields.Char(
        string="Názov",
        compute="_compute_display_name",
    )

    _unique_employee_year = models.Constraint(
        "UNIQUE(employee_id, year)",
        "Pre zamestnanca môže existovať len jedno hodnotenie za rok.",
    )

    @api.depends("employee_id.name", "year")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.employee_id.display_name or '-'} / {rec.year or '-'}"

    @api.depends("year")
    def _compute_year_display(self):
        for rec in self:
            rec.year_display = str(rec.year or "")

    def _inverse_year_display(self):
        for rec in self:
            value = (rec.year_display or "").strip()
            rec.year = int(value) if value else 0

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for rec in self:
            if rec.employee_id and not rec.manager_id:
                rec.manager_id = rec.employee_id.parent_id

    @api.constrains("year")
    def _check_year(self):
        current_year = fields.Date.context_today(self).year
        for rec in self:
            if rec.year < 2000 or rec.year > current_year + 5:
                raise ValidationError("Rok hodnotenia musí byť v rozumnom rozsahu.")

    @api.model_create_multi
    def create(self, vals_list):
        self._tenenet_check_evaluation_write_access()
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            if normalized_vals.get("employee_id") and not normalized_vals.get("manager_id"):
                employee = self.env["hr.employee"].browse(normalized_vals["employee_id"])
                normalized_vals["manager_id"] = employee.parent_id.id or False
            normalized_vals_list.append(normalized_vals)
        return super().create(normalized_vals_list)

    def write(self, vals):
        self._tenenet_check_evaluation_write_access()
        return super().write(vals)

    def unlink(self):
        self._tenenet_check_evaluation_write_access()
        return super().unlink()

    def _tenenet_check_evaluation_write_access(self):
        if self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager"):
            return
        raise UserError(_("Ročné hodnotenia môže upravovať iba HR administrátor."))
