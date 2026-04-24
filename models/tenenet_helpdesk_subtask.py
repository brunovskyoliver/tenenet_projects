from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command
from odoo.tools import format_datetime


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
    seen_ids = fields.One2many(
        "tenenet.helpdesk.subtask.seen",
        "subtask_id",
        string="Videnia",
        readonly=True,
    )
    assigned_employee_count = fields.Integer(
        string="Počet pridelených",
        compute="_compute_seen_info",
        export_string_translation=False,
    )
    single_seen_display = fields.Char(
        string="Videné",
        compute="_compute_seen_info",
        export_string_translation=False,
    )
    seen_detail_html = fields.Html(
        string="Prehľad videní",
        compute="_compute_seen_info",
        export_string_translation=False,
        sanitize=True,
    )
    can_view_seen_info = fields.Boolean(
        string="Môže vidieť videnia",
        compute="_compute_seen_info",
        export_string_translation=False,
    )
    show_seen_display = fields.Boolean(
        string="Zobraziť stav videnia",
        compute="_compute_seen_info",
        export_string_translation=False,
    )
    show_seen_button = fields.Boolean(
        string="Zobraziť tlačidlo videní",
        compute="_compute_seen_info",
        export_string_translation=False,
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

    @api.depends("employee_ids", "employee_ids.user_id", "seen_ids", "seen_ids.seen_at", "seen_ids.user_id", "ticket_id.tenenet_requested_by_user_id", "create_uid")
    @api.depends_context("uid", "tz", "lang")
    def _compute_seen_info(self):
        for subtask in self:
            can_view_seen_info = subtask._user_can_view_seen_info(self.env.user)
            employee_count = len(subtask.employee_ids)
            subtask.assigned_employee_count = employee_count
            subtask.can_view_seen_info = can_view_seen_info
            subtask.show_seen_display = bool(can_view_seen_info)
            subtask.show_seen_button = False

            if not can_view_seen_info:
                subtask.single_seen_display = False
                subtask.seen_detail_html = False
                continue
            if not subtask.employee_ids:
                subtask.single_seen_display = _("Nevidené")
                subtask.seen_detail_html = False
                continue

            seen_by_user = {
                seen.user_id.id: seen
                for seen in subtask.sudo().seen_ids
            }
            trackable_employees = subtask.employee_ids.filtered("user_id")
            seen_count = len([
                employee
                for employee in trackable_employees
                if employee.user_id.id in seen_by_user
            ])
            trackable_count = len(trackable_employees)

            if employee_count == 1:
                employee = subtask.employee_ids[:1]
                if not employee.user_id:
                    subtask.single_seen_display = _("Bez používateľa")
                else:
                    seen = seen_by_user.get(employee.user_id.id)
                    subtask.single_seen_display = (
                        format_datetime(subtask.env, seen.seen_at)
                        if seen
                        else _("Nevidené")
                    )
            elif not trackable_count:
                subtask.single_seen_display = _("Bez používateľov")
            elif not seen_count:
                subtask.single_seen_display = _("Nikto nevidel (0/%(total)s)", total=trackable_count)
            elif seen_count == trackable_count:
                subtask.single_seen_display = _("Všetci videli (%(seen)s/%(total)s)", seen=seen_count, total=trackable_count)
            else:
                subtask.single_seen_display = _("Čiastočne videné (%(seen)s/%(total)s)", seen=seen_count, total=trackable_count)

            subtask.seen_detail_html = subtask._get_seen_detail_html(seen_by_user)

    def _get_seen_detail_html(self, seen_by_user):
        self.ensure_one()
        rows = []
        for employee in self.employee_ids:
            user = employee.user_id
            seen = seen_by_user.get(user.id) if user else False
            if not user:
                status = _("Bez používateľa")
                seen_at = ""
            elif seen:
                status = _("Áno")
                seen_at = format_datetime(self.env, seen.seen_at)
            else:
                status = _("Nie")
                seen_at = ""
            rows.append(
                "<tr>"
                f"<td>{escape(employee.display_name)}</td>"
                f"<td>{escape(user.display_name if user else '')}</td>"
                f"<td>{escape(status)}</td>"
                f"<td>{escape(seen_at)}</td>"
                "</tr>"
            )
        return Markup(
            "<table class='table table-sm table-hover mb-0'>"
            "<thead><tr>"
            f"<th>{escape(_('Zamestnanec'))}</th>"
            f"<th>{escape(_('Používateľ'))}</th>"
            f"<th>{escape(_('Videl'))}</th>"
            f"<th>{escape(_('Čas videnia'))}</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

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

    def _user_can_view_seen_info(self, user):
        self.ensure_one()
        return bool(
            self.env.is_superuser()
            or self._user_is_helpdesk_manager(user)
            or self.ticket_id.tenenet_requested_by_user_id == user
            or self.create_uid == user
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

    def _check_seen_info_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        for subtask in self:
            if not subtask._user_can_view_seen_info(current_user):
                raise AccessError(
                    _("Videnia čiastkovej úlohy môže vidieť iba autor úlohy, vlastník požiadavky alebo TENENET helpdesk manažér.")
                )

    def _mark_seen_for_user(self, user):
        self.ensure_one()
        if user not in self.user_ids:
            return self.env["tenenet.helpdesk.subtask.seen"]
        seen_model = self.env["tenenet.helpdesk.subtask.seen"]
        seen = seen_model.search([
            ("subtask_id", "=", self.id),
            ("user_id", "=", user.id),
        ], limit=1)
        if seen:
            return seen
        return seen_model.create({
            "subtask_id": self.id,
            "user_id": user.id,
        })

    def _mark_seen_from_tab_context(self):
        if not self.env.context.get("tenenet_mark_seen_on_subtask_tab_open"):
            return
        for subtask in self:
            subtask._mark_seen_for_user(self.env.user)

    def _prepare_seen_wizard_lines(self):
        self.ensure_one()
        seen_by_user = {
            seen.user_id.id: seen
            for seen in self.sudo().seen_ids
        }
        line_commands = []
        for employee in self.employee_ids:
            user = employee.user_id
            seen = seen_by_user.get(user.id) if user else False
            line_commands.append(Command.create({
                "employee_id": employee.id,
                "user_id": user.id if user else False,
                "has_user": bool(user),
                "has_seen": bool(seen),
                "seen_at": seen.seen_at if seen else False,
            }))
        return line_commands

    def action_tenenet_open_subtask_form(self):
        self.ensure_one()
        self._check_read_access()
        view = self.env.ref("tenenet_projects.view_tenenet_helpdesk_subtask_form")
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": {
                "default_ticket_id": self.ticket_id.id,
            },
        }

    def action_open_seen_wizard(self):
        self.ensure_one()
        self._check_seen_info_access()
        wizard = self.env["tenenet.helpdesk.subtask.seen.wizard"].create({
            "subtask_id": self.id,
            "line_ids": self._prepare_seen_wizard_lines(),
        })
        view = self.env.ref("tenenet_projects.view_tenenet_helpdesk_subtask_seen_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Kto videl"),
            "res_model": "tenenet.helpdesk.subtask.seen.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
        }

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
        self._mark_seen_from_tab_context()
        return super().read(fields=fields, load=load)

    def web_read(self, specification):
        self._check_read_access()
        self._mark_seen_from_tab_context()
        return super().web_read(specification)

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


class TenenetHelpdeskSubtaskSeen(models.Model):
    _name = "tenenet.helpdesk.subtask.seen"
    _description = "Videnie čiastkovej úlohy"
    _order = "seen_at, id"

    subtask_id = fields.Many2one(
        "tenenet.helpdesk.subtask",
        string="Čiastková úloha",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Používateľ",
        required=True,
        ondelete="cascade",
        index=True,
    )
    seen_at = fields.Datetime(
        string="Videné",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    company_id = fields.Many2one(
        related="subtask_id.company_id",
        store=True,
        readonly=True,
    )

    _unique_subtask_user = models.Constraint(
        "UNIQUE(subtask_id, user_id)",
        "Používateľ môže mať k čiastkovej úlohe iba jedno videnie.",
    )

    def _check_read_access(self):
        if self.env.is_superuser():
            return
        for seen in self:
            if not seen.subtask_id._user_can_view_seen_info(self.env.user):
                raise AccessError(_("Nemáte oprávnenie čítať videnia tejto čiastkovej úlohy."))

    def _check_create_access(self, vals):
        if self.env.is_superuser():
            return
        subtask = self.env["tenenet.helpdesk.subtask"].browse(vals.get("subtask_id"))
        user = self.env["res.users"].browse(vals.get("user_id") or self.env.user.id)
        if not subtask or user != self.env.user or user not in subtask.user_ids:
            raise AccessError(_("Videnie čiastkovej úlohy sa môže zapísať iba pre aktuálne prideleného používateľa."))

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            vals.setdefault("user_id", self.env.user.id)
            vals.setdefault("seen_at", fields.Datetime.now())
            self._check_create_access(vals)
            prepared_vals_list.append(vals)
        return super().create(prepared_vals_list)

    def read(self, fields=None, load="_classic_read"):
        self._check_read_access()
        return super().read(fields=fields, load=load)

    def write(self, vals):
        if not self.env.is_superuser():
            raise AccessError(_("Videnia čiastkových úloh nie je možné upravovať."))
        return super().write(vals)

    def unlink(self):
        if not self.env.is_superuser():
            raise AccessError(_("Videnia čiastkových úloh nie je možné mazať."))
        return super().unlink()


class TenenetHelpdeskSubtaskSeenWizard(models.TransientModel):
    _name = "tenenet.helpdesk.subtask.seen.wizard"
    _description = "Prehľad videní čiastkovej úlohy"

    subtask_id = fields.Many2one(
        "tenenet.helpdesk.subtask",
        string="Čiastková úloha",
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "tenenet.helpdesk.subtask.seen.wizard.line",
        "wizard_id",
        string="Používatelia",
        readonly=True,
    )

    def _check_wizard_access(self):
        for wizard in self:
            wizard.subtask_id._check_seen_info_access()

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        wizards._check_wizard_access()
        return wizards

    def read(self, fields=None, load="_classic_read"):
        self._check_wizard_access()
        return super().read(fields=fields, load=load)


class TenenetHelpdeskSubtaskSeenWizardLine(models.TransientModel):
    _name = "tenenet.helpdesk.subtask.seen.wizard.line"
    _description = "Riadok prehľadu videní čiastkovej úlohy"
    _order = "id"

    wizard_id = fields.Many2one(
        "tenenet.helpdesk.subtask.seen.wizard",
        string="Sprievodca",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Používateľ",
        readonly=True,
    )
    has_user = fields.Boolean(
        string="Má používateľa",
        readonly=True,
    )
    has_seen = fields.Boolean(
        string="Videl",
        readonly=True,
    )
    seen_at = fields.Datetime(
        string="Čas videnia",
        readonly=True,
    )

    def read(self, fields=None, load="_classic_read"):
        self.mapped("wizard_id")._check_wizard_access()
        return super().read(fields=fields, load=load)
