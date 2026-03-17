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

    _unique_project_leave_type = models.Constraint(
        "UNIQUE(project_id, leave_type_id)",
        "Pre daný projekt môže existovať len jedno pravidlo pre každý typ dovolenky.",
    )
