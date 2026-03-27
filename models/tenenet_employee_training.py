from odoo import fields, models


class TenenetEmployeeTraining(models.Model):
    _name = "tenenet.employee.training"
    _description = "Školenie zamestnanca"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, certificate_date desc, name"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    name = fields.Char(string="Názov školenia", required=True, tracking=True)
    training_type = fields.Selection(
        [("internal", "Interné"), ("external", "Externé")],
        string="Typ školenia",
        required=True,
        default="external",
        tracking=True,
    )
    provider = fields.Char(string="Poskytovateľ", tracking=True)
    date_from = fields.Date(string="Od", tracking=True)
    date_to = fields.Date(string="Do", tracking=True)
    certificate_date = fields.Date(string="Dátum certifikátu", tracking=True)
    notes = fields.Text(string="Poznámka")
    active = fields.Boolean(string="Aktívne", default=True)
