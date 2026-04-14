from odoo import fields, models, _
from odoo.exceptions import UserError


class TenenetEmployeeAssetHandoverWizard(models.TransientModel):
    _name = "tenenet.employee.asset.handover.wizard"
    _description = "Sprievodca pridaním firemného majetku"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        default=lambda self: self.env.context.get("default_employee_id") or self.env.context.get("active_id"),
    )
    handover_date = fields.Date(
        string="Termín odovzdania",
        required=True,
        default=fields.Date.context_today,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )
    message = fields.Html(
        string="Správa k podpisu",
        default=lambda self: _("<p>Dobrý deň,</p><p>prosíme o podpis preberacieho protokolu k odovzdanému firemnému majetku.</p>"),
    )
    note = fields.Text(string="Poznámka")
    line_ids = fields.One2many(
        "tenenet.employee.asset.handover.wizard.line",
        "wizard_id",
        string="Majetok",
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Pridajte aspoň jednu položku majetku."))
        if not self.employee_id.work_email:
            raise UserError(_("Zamestnanec %s nemá vyplnený pracovný email.", self.employee_id.name))

        handover = self.env["tenenet.employee.asset.handover"].create({
            "employee_id": self.employee_id.id,
            "handover_date": self.handover_date,
            "note": self.note,
        })
        self.env["tenenet.employee.asset"].create([
            {
                "employee_id": self.employee_id.id,
                "asset_type_id": line.asset_type_id.id,
                "serial_number": line.serial_number,
                "handover_date": self.handover_date,
                "handover_id": handover.id,
                "currency_id": self.currency_id.id,
                "cost": line.cost,
                "note": line.note,
            }
            for line in self.line_ids
        ])
        handover.action_send_for_signature(message=self.message)

        return {
            "type": "ir.actions.act_window",
            "name": _("Preberací protokol"),
            "res_model": "tenenet.employee.asset.handover",
            "res_id": handover.id,
            "view_mode": "form",
            "target": "current",
        }


class TenenetEmployeeAssetHandoverWizardLine(models.TransientModel):
    _name = "tenenet.employee.asset.handover.wizard.line"
    _description = "Položka firemného majetku v sprievodcovi"

    wizard_id = fields.Many2one(
        "tenenet.employee.asset.handover.wizard",
        required=True,
        ondelete="cascade",
    )
    asset_type_id = fields.Many2one(
        "tenenet.employee.asset.type",
        string="Typ majetku",
        required=True,
        ondelete="restrict",
    )
    serial_number = fields.Char(
        string="Výrobné číslo",
        required=True,
    )
    currency_id = fields.Many2one(
        related="wizard_id.currency_id",
        readonly=True,
    )
    cost = fields.Monetary(
        string="Hodnota (€)",
        currency_field="currency_id",
        default=0.0,
    )
    note = fields.Text(string="Poznámka")
