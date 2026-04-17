from odoo import api, fields, models, _
from odoo.exceptions import AccessError

from .tenenet_onboarding_task_template import (
    PHASE_SELECTION,
    RESPONSIBLE_ROLE_SELECTION,
)


class TenenetOnboardingTask(models.Model):
    _name = "tenenet.onboarding.task"
    _description = "Úloha onboarding procesu"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "phase_sequence, sequence, id"

    onboarding_id = fields.Many2one(
        "tenenet.onboarding",
        string="Onboarding proces",
        required=True,
        ondelete="cascade",
    )
    name = fields.Text(
        string="Úloha",
        required=True,
    )
    phase = fields.Selection(
        PHASE_SELECTION,
        string="Fáza",
        required=True,
    )
    phase_sequence = fields.Integer(
        string="Poradie fázy",
        store=True,
    )
    sequence = fields.Integer(
        string="Poradie",
        default=10,
    )
    responsible_role = fields.Selection(
        RESPONSIBLE_ROLE_SELECTION,
        string="Zodpovedná rola",
    )
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Zodpovedná osoba",
    )
    state = fields.Selection(
        [
            ("todo", "Na realizáciu"),
            ("done", "Hotovo"),
            ("skipped", "Preskočené"),
            ("not_applicable", "Nevzťahuje sa"),
        ],
        string="Stav",
        default="todo",
        required=True,
        tracking=True,
    )
    done_by_user_id = fields.Many2one(
        "res.users",
        string="Splnil",
        readonly=True,
        copy=False,
        tracking=True,
    )
    done_date = fields.Datetime(
        string="Dátum splnenia",
        readonly=True,
        copy=False,
    )
    is_mandatory = fields.Boolean(
        string="Povinná",
        default=True,
    )
    template_id = fields.Many2one(
        "tenenet.onboarding.task.template",
        string="Šablóna",
        readonly=True,
        ondelete="set null",
    )
    note = fields.Text(string="Poznámka")

    def _check_task_write_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        ticket_model = self.env["helpdesk.ticket"]
        is_editor = ticket_model._user_has_tenenet_helpdesk_editor_role(current_user)
        is_manager = ticket_model._user_has_tenenet_helpdesk_manager_role(current_user)
        for task in self:
            if is_manager or is_editor:
                continue
            if task.responsible_user_id and task.responsible_user_id != current_user:
                raise AccessError(
                    _("Úlohu môže označiť iba zodpovedná osoba alebo TENENET helpdesk editor.")
                )

    def write(self, vals):
        if "state" in vals:
            self._check_task_write_access()
            if vals["state"] == "done":
                for task in self:
                    if task.state != "done":
                        vals_with_meta = dict(vals)
                        vals_with_meta["done_by_user_id"] = self.env.user.id
                        vals_with_meta["done_date"] = fields.Datetime.now()
                        super(TenenetOnboardingTask, task).write(vals_with_meta)
                        task.onboarding_id._recompute_progress()
                return True
            else:
                result = super().write(vals)
                for task in self:
                    task.onboarding_id._recompute_progress()
                return result
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        from .tenenet_onboarding_task_template import PHASE_SEQUENCE
        for vals in vals_list:
            if "phase" in vals and "phase_sequence" not in vals:
                vals["phase_sequence"] = PHASE_SEQUENCE.get(vals["phase"], 99)
        return super().create(vals_list)

    # --------------------------------------------------------------------------
    # State action buttons
    # --------------------------------------------------------------------------

    def action_mark_done(self):
        self.ensure_one()
        self.write({"state": "done"})
        return self._next_todo_task_action()

    def _next_todo_task_action(self):
        self.ensure_one()
        next_task = self.env["tenenet.onboarding.task"].search([
            ("onboarding_id", "=", self.onboarding_id.id),
            ("state", "=", "todo"),
            ("id", "!=", self.id),
        ], order="phase_sequence, sequence, id", limit=1)
        if next_task:
            return {
                "type": "ir.actions.act_window",
                "res_model": "tenenet.onboarding.task",
                "res_id": next_task.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}

    def action_skip(self):
        self.ensure_one()
        self.write({"state": "skipped"})
        return self._next_todo_task_action()

    def action_mark_not_applicable(self):
        self.ensure_one()
        self.write({"state": "not_applicable"})
        return self._next_todo_task_action()

    def action_reset_todo(self):
        self.write({"state": "todo"})
