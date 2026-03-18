from odoo import fields, models


class TenenetUtilizationSyncWizard(models.TransientModel):
    _name = "tenenet.utilization.sync.wizard"
    _description = "Synchronizácia vyťaženosti za mesiace"

    date_from = fields.Date(
        string="Od mesiaca",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="Do mesiaca",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )

    def action_sync(self):
        self.ensure_one()
        self.env["tenenet.utilization"]._sync_for_period_range(
            self.date_from,
            self.date_to,
        )
        return {"type": "ir.actions.act_window_close"}
