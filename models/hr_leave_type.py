from odoo import fields, models

from .tenenet_project_timesheet import HOUR_TYPE_SELECTION


# Filter only leave-scope hour types for the selection
LEAVE_HOUR_TYPE_SELECTION = [
    ("vacation", "Dovolenka"),
    ("sick", "PN/OČR"),
    ("doctor", "Lekár"),
    ("holidays", "Sviatky"),
]


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    tenenet_hour_type = fields.Selection(
        LEAVE_HOUR_TYPE_SELECTION,
        string="Tenenet typ hodín",
        help="Mapovanie typu dovolenky na kategóriu hodín v Tenenet timesheetoch. "
             "Ak nie je nastavené, systém sa pokúsi odvodiť typ z názvu.",
    )
    is_tenenet_leave = fields.Boolean(
        string="Je Tenenet dovolenka",
        default=False,
        help="Označuje, že tento typ dovolenky je spravovaný modulom Tenenet Projects.",
    )
