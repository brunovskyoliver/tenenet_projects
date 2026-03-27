from odoo import fields, models


class TenenetProjectLeaveRule(models.Model):
    _name = "tenenet.project.leave.rule"
    _description = "Pravidlo dovolenky pre projekt"
    _order = "project_id, leave_type_id"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Typ dovolenky",
        required=True,
        ondelete="cascade",
    )
    included = fields.Boolean(
        string="Zahrnuté do projektu",
        default=True,
        help="Ak áno, hodiny tohto typu absencie sa fakturujú projektu. "
             "Ak nie, idú do súhrnu Tenenet.",
    )
    max_leaves_per_year_days = fields.Float(
        string="Max. dní za rok",
        digits=(10, 2),
        default=0.0,
        help="Maximálny počet dní tohto typu dovolenky za rok pre jedného zamestnanca na projekte. "
             "0 = bez limitu.",
    )

    _unique_project_leave_type = models.Constraint(
        "UNIQUE(project_id, leave_type_id)",
        "Pre daný projekt môže existovať len jedno pravidlo pre každý typ dovolenky.",
    )
