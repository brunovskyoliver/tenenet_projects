from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command


class TenenetHelpdeskSubtask(models.Model):
    _name = "tenenet.helpdesk.subtask"
    _description = "Čiastková úloha helpdesk požiadavky"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(
        string="Úloha",
        required=True,
        tracking=True,
    )
    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk požiadavka",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Poradie",
        default=10,
    )
    priority = fields.Selection(
        [
            ("0", "Nízka priorita"),
            ("1", "Stredná priorita"),
            ("2", "Vysoká priorita"),
            ("3", "Urgentné"),
        ],
        string="Priorita",
        default="0",
        tracking=True,
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "tenenet_helpdesk_subtask_hr_employee_rel",
        "subtask_id",
        "employee_id",
        string="Pridelená osoba",
        required=True,
        tracking=True,
    )
    user_ids = fields.Many2many(
        "res.users",
        compute="_compute_user_ids",
        string="Pridelení používatelia",
        store=True,
        readonly=True,
    )
    is_done = fields.Boolean(
        string="Hotovo",
        default=False,
        tracking=True,
    )
    description = fields.Html(string="Popis")
    date_deadline = fields.Date(string="Termín")
    company_id = fields.Many2one(
        related="ticket_id.company_id",
        store=True,
        readonly=True,
    )
    done_by_user_id = fields.Many2one(
        "res.users",
        string="Dokončil",
        readonly=True,
        copy=False,
        tracking=True,
    )
    done_date = fields.Datetime(
        string="Dátum dokončenia",
        readonly=True,
        copy=False,
    )

    @api.depends("employee_ids.user_id")
    def _compute_user_ids(self):
        for subtask in self:
            subtask.user_ids = [Command.set(subtask.employee_ids.mapped("user_id").filtered("id").ids)]

    @api.model
    def _helpdesk_ticket_model(self):
        return self.env["helpdesk.ticket"]

    def _user_is_helpdesk_manager(self, user):
        return self._helpdesk_ticket_model()._user_has_tenenet_helpdesk_manager_role(user)

    def _user_is_helpdesk_user(self, user):
        return self._helpdesk_ticket_model()._user_has_tenenet_helpdesk_role(user)

    def _user_can_read_subtask(self, user):
        self.ensure_one()
        ticket = self.ticket_id
        if self._user_is_helpdesk_manager(user):
            return True
        if not self._user_is_helpdesk_user(user):
            return False
        if user in self.user_ids:
            return True
        if user in (
            ticket.tenenet_requested_by_user_id
            | ticket.user_id
            | ticket.tenenet_followup_user_id
            | ticket.tenenet_control_user_id
        ):
            return True
        if user.partner_id in ticket.message_partner_ids:
            return True
        responsible_users = (
            ticket.tenenet_requested_by_user_id
            | ticket.user_id
            | ticket.tenenet_followup_user_id
            | ticket.tenenet_control_user_id
            | self.user_ids
        ).filtered("id")
        return any(
            self._helpdesk_ticket_model()._user_is_above_responsible_user(user, responsible_user)
            for responsible_user in responsible_users
        )

    def _user_can_manage_subtask(self, user):
        self.ensure_one()
        return bool(
            self._user_is_helpdesk_manager(user)
            or (
                self._user_is_helpdesk_user(user)
                and self.ticket_id.tenenet_requested_by_user_id == user
            )
        )

    def _check_read_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        for subtask in self:
            if not subtask._user_can_read_subtask(current_user):
                raise AccessError(_("Túto čiastkovú úlohu nemôžete čítať."))

    def _check_manage_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        for subtask in self:
            if not subtask._user_can_manage_subtask(current_user):
                raise AccessError(
                    _("Čiastkovú úlohu môže upravovať iba vlastník požiadavky alebo TENENET helpdesk manažér.")
                )

    def _check_done_write_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        for subtask in self:
            if not (
                subtask._user_is_helpdesk_manager(current_user)
                or current_user in subtask.user_ids
            ):
                raise AccessError(
                    _("Dokončenie čiastkovej úlohy môže meniť iba pridelená osoba alebo TENENET helpdesk manažér.")
                )

    def _check_ticket_internal(self):
        for subtask in self:
            if not subtask.ticket_id._is_tenenet_internal_team(subtask.ticket_id.team_id):
                raise ValidationError(
                    _("Čiastkové úlohy sú dostupné iba pre interné TENENET helpdesk požiadavky.")
                )

    def _check_assigned_employees(self):
        for subtask in self.sudo():
            if not subtask.employee_ids:
                raise ValidationError(_("Čiastková úloha musí mať aspoň jedného prideleného zamestnanca."))
            inactive_employees = subtask.employee_ids.filtered(lambda employee: not employee.active)
            if inactive_employees:
                raise ValidationError(
                    _(
                        "Zamestnanec %(employee)s nie je aktívny.",
                        employee=", ".join(inactive_employees.mapped("display_name")),
                    )
                )
            wrong_company_employees = subtask.employee_ids.filtered(
                lambda employee: subtask.ticket_id.company_id
                and employee.company_id
                and employee.company_id != subtask.ticket_id.company_id
            )
            if wrong_company_employees:
                raise ValidationError(
                    _(
                        "Zamestnanec %(employee)s nepatrí do spoločnosti helpdesk požiadavky.",
                        employee=", ".join(wrong_company_employees.mapped("display_name")),
                    )
                )

    def _get_default_employee_for_ticket(self, ticket):
        current_employee = self.env.user.employee_ids.filtered(lambda employee: employee.active)[:1]
        if current_employee:
            return current_employee
        requester_employee = ticket._get_tenenet_requester_user().employee_ids.filtered(lambda employee: employee.active)[:1]
        if requester_employee:
            return requester_employee
        return self.env["hr.employee"].sudo().search([
            ("active", "=", True),
            ("company_id", "in", [False, ticket.company_id.id] if ticket.company_id else [False]),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        employee_commands_by_index = []
        for vals in vals_list:
            vals = dict(vals)
            ticket = self.env["helpdesk.ticket"].browse(vals.get("ticket_id") or self.env.context.get("default_ticket_id"))
            if not ticket:
                raise ValidationError(_("Čiastková úloha musí byť priradená k helpdesk požiadavke."))
            vals["ticket_id"] = ticket.id
            if "employee_id" in vals and not vals.get("employee_ids"):
                employee_id = vals.pop("employee_id")
                vals["employee_ids"] = [Command.set([employee_id] if employee_id else [])]
            if not vals.get("employee_ids"):
                employee = self._get_default_employee_for_ticket(ticket)
                if not employee:
                    raise ValidationError(_("Čiastková úloha musí mať prideleného zamestnanca."))
                vals["employee_ids"] = [Command.set(employee.ids)]
            employee_commands_by_index.append(vals.pop("employee_ids"))
            prepared_vals_list.append(vals)
        subtasks = super().create(prepared_vals_list)
        for subtask, employee_commands in zip(subtasks, employee_commands_by_index):
            super(TenenetHelpdeskSubtask, subtask.sudo()).write({"employee_ids": employee_commands})
        subtasks._check_ticket_internal()
        subtasks._check_manage_access()
        subtasks._check_assigned_employees()
        return subtasks

    def read(self, fields=None, load="_classic_read"):
        self._check_read_access()
        return super().read(fields=fields, load=load)

    def write(self, vals):
        vals = dict(vals)
        if "employee_id" in vals and not vals.get("employee_ids"):
            employee_id = vals.pop("employee_id")
            vals["employee_ids"] = [Command.set([employee_id] if employee_id else [])]
        employee_commands = vals.pop("employee_ids", None)
        vals_without_meta = {
            field_name: value
            for field_name, value in vals.items()
            if field_name not in ("done_by_user_id", "done_date")
        }
        if set(vals_without_meta) == {"is_done"} and employee_commands is None:
            self._check_done_write_access()
        else:
            self._check_manage_access()

        if vals.get("is_done"):
            vals["done_by_user_id"] = self.env.user.id
            vals["done_date"] = fields.Datetime.now()
        elif "is_done" in vals and not vals["is_done"]:
            vals["done_by_user_id"] = False
            vals["done_date"] = False

        result = super().write(vals) if vals else True
        if employee_commands is not None:
            super(TenenetHelpdeskSubtask, self.sudo()).write({"employee_ids": employee_commands})
        if "ticket_id" in vals:
            self._check_ticket_internal()
        if employee_commands is not None or "ticket_id" in vals:
            self._check_assigned_employees()
        return result

    def unlink(self):
        self._check_manage_access()
        return super().unlink()
