from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.fields import Command
from odoo.exceptions import AccessError, UserError, ValidationError


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    _TENENET_INTERNAL_TEAM_NAME = "Interné TENENET"

    tenenet_requested_by_user_id = fields.Many2one(
        "res.users",
        string="Požiadavku vytvoril",
        tracking=True,
        copy=False,
    )
    tenenet_assignment_domain_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_tenenet_assignment_domain_user_ids",
        export_string_translation=False,
    )
    tenenet_active_assigned_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_tenenet_active_assigned_user_ids",
        store=True,
        copy=False,
        string="Aktívne pridelení",
        export_string_translation=False,
    )
    tenenet_followup_user_id = fields.Many2one(
        "res.users",
        string="Follow-up používateľ",
        tracking=True,
        copy=False,
    )
    tenenet_control_user_id = fields.Many2one(
        "res.users",
        string="Kontroluje",
        tracking=True,
        copy=False,
    )
    tenenet_followup_confirmed_by_user_id = fields.Many2one(
        "res.users",
        string="Follow-up potvrdil",
        copy=False,
        readonly=True,
    )
    tenenet_followup_confirmed_at = fields.Datetime(
        string="Follow-up potvrdený",
        copy=False,
        readonly=True,
    )
    tenenet_control_confirmed_by_user_id = fields.Many2one(
        "res.users",
        string="Kontrolu potvrdil",
        copy=False,
        readonly=True,
    )
    tenenet_control_confirmed_at = fields.Datetime(
        string="Kontrola potvrdená",
        copy=False,
        readonly=True,
    )
    tenenet_is_internal_team = fields.Boolean(
        compute="_compute_tenenet_role_flags",
        export_string_translation=False,
    )
    tenenet_is_helpdesk_user = fields.Boolean(
        compute="_compute_tenenet_role_flags",
        export_string_translation=False,
    )
    tenenet_is_helpdesk_editor = fields.Boolean(
        compute="_compute_tenenet_role_flags",
        export_string_translation=False,
    )
    tenenet_is_helpdesk_manager = fields.Boolean(
        compute="_compute_tenenet_role_flags",
        export_string_translation=False,
    )
    tenenet_can_confirm_followup = fields.Boolean(
        compute="_compute_tenenet_confirmation_flags",
        export_string_translation=False,
    )
    tenenet_can_confirm_control = fields.Boolean(
        compute="_compute_tenenet_confirmation_flags",
        export_string_translation=False,
    )

    @api.depends("team_id", "team_id.name")
    @api.depends_context("uid")
    def _compute_tenenet_role_flags(self):
        current_user = self.env.user
        is_manager = self._user_has_tenenet_helpdesk_manager_role(current_user)
        is_editor = self._user_has_tenenet_helpdesk_editor_role(current_user)
        is_user = self._user_has_tenenet_helpdesk_role(current_user)
        for ticket in self:
            ticket.tenenet_is_internal_team = ticket._is_tenenet_internal_team(ticket.team_id)
            ticket.tenenet_is_helpdesk_manager = is_manager
            ticket.tenenet_is_helpdesk_editor = is_editor
            ticket.tenenet_is_helpdesk_user = is_user

    @api.depends(
        "team_id",
        "team_id.name",
        "tenenet_requested_by_user_id",
        "tenenet_requested_by_user_id.employee_ids",
        "tenenet_requested_by_user_id.employee_ids.parent_id",
        "tenenet_requested_by_user_id.employee_ids.parent_id.user_id",
        "tenenet_requested_by_user_id.employee_ids.parent_id.parent_id",
        "tenenet_requested_by_user_id.employee_ids.parent_id.parent_id.user_id",
        "domain_user_ids",
    )
    def _compute_tenenet_assignment_domain_user_ids(self):
        for ticket in self:
            if ticket._is_tenenet_internal_team(ticket.team_id):
                requester = ticket._get_tenenet_requester_user()
                users = ticket._get_tenenet_allowed_assignment_users_for_user(
                    requester,
                    team=ticket.team_id,
                )
            else:
                users = ticket.domain_user_ids.filtered(lambda user: not user.share)
            ticket.tenenet_assignment_domain_user_ids = [Command.set(users.ids)]

    @api.depends(
        "team_id",
        "team_id.name",
        "user_id",
        "kanban_state",
        "tenenet_followup_user_id",
        "tenenet_control_user_id",
    )
    def _compute_tenenet_active_assigned_user_ids(self):
        for ticket in self:
            active_users = ticket.user_id
            if ticket._is_tenenet_internal_team(ticket.team_id):
                if ticket.kanban_state == "blocked":
                    active_users |= ticket.tenenet_followup_user_id
                elif ticket.kanban_state == "done":
                    active_users |= ticket.tenenet_control_user_id
            ticket.tenenet_active_assigned_user_ids = [Command.set(active_users.filtered("id").ids)]

    @api.depends(
        "team_id",
        "team_id.name",
        "kanban_state",
        "tenenet_followup_user_id",
        "tenenet_control_user_id",
    )
    @api.depends_context("uid")
    def _compute_tenenet_confirmation_flags(self):
        current_user = self.env.user
        is_manager = self._user_has_tenenet_helpdesk_manager_role(current_user)
        for ticket in self:
            ticket.tenenet_can_confirm_followup = bool(
                ticket._is_tenenet_internal_team(ticket.team_id)
                and ticket.kanban_state == "blocked"
                and ticket.tenenet_followup_user_id
                and (is_manager or ticket.tenenet_followup_user_id == current_user)
            )
            ticket.tenenet_can_confirm_control = bool(
                ticket._is_tenenet_internal_team(ticket.team_id)
                and ticket.kanban_state == "done"
                and ticket.tenenet_control_user_id
                and (is_manager or ticket.tenenet_control_user_id == current_user)
            )

    @api.model
    def _get_tenenet_internal_team(self, company=False):
        domain = [("name", "=", self._TENENET_INTERNAL_TEAM_NAME)]
        if company:
            domain.insert(0, ("company_id", "=", company.id))
        return self.env["helpdesk.team"].sudo().search(domain, limit=1)

    @api.model
    def _is_tenenet_internal_team(self, team):
        return bool(team and team.name == self._TENENET_INTERNAL_TEAM_NAME)

    @api.model
    def _user_has_tenenet_helpdesk_role(self, user):
        return bool(
            user
            and (
                user.has_group("tenenet_projects.group_tenenet_helpdesk_user")
                or user.has_group("tenenet_projects.group_tenenet_helpdesk_editor")
                or user.has_group("tenenet_projects.group_tenenet_helpdesk_manager")
            )
        )

    @api.model
    def _user_has_tenenet_helpdesk_editor_role(self, user):
        return bool(
            user
            and (
                user.has_group("tenenet_projects.group_tenenet_helpdesk_editor")
                or user.has_group("tenenet_projects.group_tenenet_helpdesk_manager")
            )
        )

    @api.model
    def _user_has_tenenet_helpdesk_manager_role(self, user):
        return bool(
            user and user.has_group("tenenet_projects.group_tenenet_helpdesk_manager")
        )

    @api.model
    def _get_tenenet_allowed_assignment_users_for_user(self, requester_user, team=False):
        if not requester_user:
            requester_user = self.env.user
        allowed_users = requester_user
        employees = self.env["hr.employee"].sudo().search([
            ("user_id", "=", requester_user.id),
        ])
        direct_managers = employees.mapped("parent_id")
        grand_managers = direct_managers.mapped("parent_id")
        allowed_users |= direct_managers.mapped("user_id")
        allowed_users |= grand_managers.mapped("user_id")
        allowed_users = allowed_users.filtered(
            lambda user: user.active
            and not user.share
            and self._user_has_tenenet_helpdesk_role(user)
            and user.has_group("helpdesk.group_helpdesk_user")
        )
        if team and team.company_id:
            allowed_users = allowed_users.filtered(
                lambda user: team.company_id in user.company_ids
            )
        return allowed_users

    def _get_tenenet_requester_user(self):
        self.ensure_one()
        return self.tenenet_requested_by_user_id or self.env.user

    @api.model
    def _get_target_team_from_vals(self, vals):
        team_id = vals.get("team_id") or self.env.context.get("default_team_id")
        if not team_id:
            team_id = self._default_team_id()
        return self.env["helpdesk.team"].browse(team_id)

    @api.model
    def _prepare_tenenet_create_vals(self, vals):
        vals = dict(vals)
        team = self._get_target_team_from_vals(vals)
        if not self._is_tenenet_internal_team(team):
            return vals

        requester_id = (
            vals.get("tenenet_requested_by_user_id")
            or self.env.context.get("tenenet_requested_by_user_id")
            or self.env.user.id
        )
        requester = self.env["res.users"].browse(requester_id)
        vals.setdefault("tenenet_requested_by_user_id", requester.id)
        vals.setdefault("user_id", requester.id)
        if (
            not self.env.is_superuser()
            and not self.env.context.get("allow_tenenet_internal_system_create")
        ):
            if requester != self.env.user:
                raise ValidationError(
                    _("Pole 'Požiadavku vytvoril' musí pri ručnom vytvorení zodpovedať prihlásenému používateľovi.")
                )
            if not self._user_has_tenenet_helpdesk_role(requester):
                raise AccessError(
                    _("Interné TENENET helpdesk požiadavky môže vytvárať iba používateľ s rolou TENENET helpdesk.")
                )
        if vals.get("kanban_state") == "blocked":
            vals["tenenet_followup_confirmed_by_user_id"] = False
            vals["tenenet_followup_confirmed_at"] = False
        if vals.get("kanban_state") == "done":
            vals["tenenet_control_confirmed_by_user_id"] = False
            vals["tenenet_control_confirmed_at"] = False
        return vals

    def _get_tenenet_result_user(self, vals, field_name):
        self.ensure_one()
        if field_name in vals:
            return self.env["res.users"].browse(vals.get(field_name))
        return self[field_name]

    def _check_tenenet_assignment_user(self, field_name, user):
        self.ensure_one()
        if self.env.context.get("allow_tenenet_internal_system_create"):
            if field_name == "user_id" and not user:
                raise ValidationError(
                    _("Interná TENENET helpdesk požiadavka musí mať prideleného používateľa.")
                )
            return
        if field_name == "user_id" and not user:
            raise ValidationError(
                _("Interná TENENET helpdesk požiadavka musí mať prideleného používateľa.")
            )
        if not user:
            return

        requester = self._get_tenenet_requester_user()
        allowed_users = self._get_tenenet_allowed_assignment_users_for_user(
            requester,
            team=self.team_id,
        )
        if user not in allowed_users:
            raise ValidationError(
                _(
                    "Používateľ %(user)s nie je povolený pre pole %(field)s. "
                    "Priradiť možno iba sebe, nadriadenému alebo nadriadenému nadriadeného.",
                    user=user.display_name,
                    field=self._fields[field_name].string,
                )
            )

    @api.model
    def _user_is_above_responsible_user(self, current_user, responsible_user):
        employees = self.env["hr.employee"].sudo().search([
            ("user_id", "=", responsible_user.id),
        ])
        return any(
            current_user in employee.service_manager_user_ids
            for employee in employees
        )

    def _user_can_write_tenenet_ticket(self, current_user):
        self.ensure_one()
        if self._user_has_tenenet_helpdesk_manager_role(current_user):
            return True
        if self._user_has_tenenet_helpdesk_editor_role(current_user):
            return True
        if not self._user_has_tenenet_helpdesk_role(current_user):
            return False
        if current_user in (
            self.tenenet_requested_by_user_id
            | self.user_id
            | self.tenenet_followup_user_id
            | self.tenenet_control_user_id
        ):
            return True
        if current_user.partner_id in self.message_partner_ids:
            return True
        responsible_users = (
            self.tenenet_requested_by_user_id
            | self.user_id
            | self.tenenet_followup_user_id
            | self.tenenet_control_user_id
        ).filtered("id")
        return any(
            self._user_is_above_responsible_user(current_user, responsible_user)
            for responsible_user in responsible_users
        )

    def _check_tenenet_write_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        for ticket in self.filtered(lambda rec: rec._is_tenenet_internal_team(rec.team_id)):
            if not ticket._user_can_write_tenenet_ticket(current_user):
                raise AccessError(
                    _("Túto internú TENENET helpdesk požiadavku nemôžete upravovať.")
                )

    def _check_tenenet_unlink_access(self):
        if self.env.is_superuser():
            return
        if self.filtered(lambda rec: rec._is_tenenet_internal_team(rec.team_id)) and not self._user_has_tenenet_helpdesk_manager_role(self.env.user):
            raise AccessError(
                _("Interné TENENET helpdesk požiadavky môže mazať iba TENENET helpdesk manažér.")
            )

    def _prepare_tenenet_write_vals(self, vals):
        vals = dict(vals)
        if "tenenet_followup_user_id" in vals or vals.get("kanban_state") == "blocked":
            vals["tenenet_followup_confirmed_by_user_id"] = False
            vals["tenenet_followup_confirmed_at"] = False
        if "tenenet_control_user_id" in vals or vals.get("kanban_state") == "done":
            vals["tenenet_control_confirmed_by_user_id"] = False
            vals["tenenet_control_confirmed_at"] = False
        return vals

    def _check_tenenet_ticket_constraints(self, vals, is_create=False):
        current_user = self.env.user
        is_manager = self.env.is_superuser() or self._user_has_tenenet_helpdesk_manager_role(current_user)
        for ticket in self.filtered(lambda rec: rec._is_tenenet_internal_team(rec.team_id)):
            if (
                "tenenet_requested_by_user_id" in vals
                and not self.env.context.get("allow_tenenet_requester_write")
                and not is_create
                and vals.get("tenenet_requested_by_user_id") != ticket.tenenet_requested_by_user_id.id
            ):
                raise ValidationError(
                    _("Pole 'Požiadavku vytvoril' nie je možné po vytvorení meniť.")
                )

            target_state = vals.get("kanban_state", ticket.kanban_state)
            if not is_manager and not self.env.context.get("allow_tenenet_confirmation_transition"):
                if "stage_id" in vals and vals.get("stage_id") != ticket.stage_id.id:
                    if ticket.kanban_state in ("blocked", "done") or target_state in ("blocked", "done"):
                        raise UserError(
                            _("Počas follow-upu alebo kontroly nie je možné meniť fázu požiadavky.")
                        )
                if ticket.kanban_state == "blocked" and target_state != "blocked":
                    raise UserError(
                        _("Požiadavka vyžadujúca follow-up môže pokračovať až po potvrdení follow-up používateľom.")
                    )
                if ticket.kanban_state == "done" and target_state != "done":
                    raise UserError(
                        _("Požiadavka vyžadujúca kontrolu môže pokračovať až po potvrdení kontrolujúcim používateľom.")
                    )

            target_user = ticket._get_tenenet_result_user(vals, "user_id")
            target_followup_user = ticket._get_tenenet_result_user(vals, "tenenet_followup_user_id")
            target_control_user = ticket._get_tenenet_result_user(vals, "tenenet_control_user_id")

            if "user_id" in vals or not ticket.user_id:
                ticket._check_tenenet_assignment_user("user_id", target_user)
            if (
                target_followup_user
                and (
                    "tenenet_followup_user_id" in vals
                    or ("kanban_state" in vals and target_state == "blocked")
                )
            ):
                ticket._check_tenenet_assignment_user("tenenet_followup_user_id", target_followup_user)
            if (
                target_control_user
                and (
                    "tenenet_control_user_id" in vals
                    or ("kanban_state" in vals and target_state == "done")
                )
            ):
                ticket._check_tenenet_assignment_user("tenenet_control_user_id", target_control_user)

            if target_state == "blocked" and not target_followup_user:
                raise ValidationError(
                    _("Pri stave 'Vyžaduje follow-up' musíte vybrať používateľa pre follow-up.")
                )
            if target_state == "done" and not target_control_user:
                raise ValidationError(
                    _("Pri stave 'Vyžaduje kontrolu' musíte vybrať používateľa na kontrolu.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = [self._prepare_tenenet_create_vals(vals) for vals in vals_list]
        tickets = super().create(prepared_vals_list)
        for ticket, ticket_vals in zip(tickets, prepared_vals_list):
            if ticket._is_tenenet_internal_team(ticket.team_id):
                ticket._check_tenenet_ticket_constraints(ticket_vals, is_create=True)
        return tickets

    def write(self, vals):
        vals = self._prepare_tenenet_write_vals(vals)
        self._check_tenenet_write_access()
        self._check_tenenet_ticket_constraints(vals)

        if "stage_id" in vals and not self.env.context.get("allow_handover_stage_write"):
            target_stage_id = vals.get("stage_id")
            tickets_with_manual_stage_change = self.filtered(
                lambda ticket: ticket.stage_id.id != target_stage_id
            )
            if tickets_with_manual_stage_change:
                locked_handover_tickets = self.env["tenenet.employee.asset.handover"].sudo().search([
                    ("helpdesk_ticket_id", "in", tickets_with_manual_stage_change.ids),
                ])
                if locked_handover_tickets:
                    raise UserError(_(
                        "Stav helpdesk požiadavky pre preberací protokol nie je možné meniť ručne. "
                        "Požiadavka sa uzatvorí automaticky po podpise dokumentu."
                    ))
        return super().write(vals)

    def unlink(self):
        self._check_tenenet_unlink_access()
        return super().unlink()

    def action_tenenet_confirm_followup(self):
        self.ensure_one()
        if not self.tenenet_can_confirm_followup:
            raise AccessError(_("Follow-up môže potvrdiť iba určený používateľ alebo TENENET helpdesk manažér."))
        self.with_context(
            allow_tenenet_confirmation_transition=True,
        ).write({
            "tenenet_followup_confirmed_by_user_id": self.env.user.id,
            "tenenet_followup_confirmed_at": fields.Datetime.now(),
            "kanban_state": "normal",
        })
        return True

    def action_tenenet_confirm_control(self):
        self.ensure_one()
        if not self.tenenet_can_confirm_control:
            raise AccessError(_("Kontrolu môže potvrdiť iba určený používateľ alebo TENENET helpdesk manažér."))
        self.with_context(
            allow_tenenet_confirmation_transition=True,
        ).write({
            "tenenet_control_confirmed_by_user_id": self.env.user.id,
            "tenenet_control_confirmed_at": fields.Datetime.now(),
            "kanban_state": "normal",
        })
        return True

    def _action_open_tenenet_request_wizard(self, request_type):
        self.ensure_one()
        if not self._is_tenenet_internal_team(self.team_id):
            raise UserError(_("Táto akcia je dostupná iba pre tím Interné TENENET."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vyžiadať follow-up") if request_type == "followup" else _("Vyžiadať kontrolu"),
            "res_model": "tenenet.helpdesk.ticket.state.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_ticket_id": self.id,
                "default_request_type": request_type,
                "active_id": self.id,
                "active_ids": self.ids,
                "active_model": self._name,
            },
        }

    def action_open_tenenet_followup_wizard(self):
        self.ensure_one()
        return self._action_open_tenenet_request_wizard("followup")

    def action_open_tenenet_control_wizard(self):
        self.ensure_one()
        return self._action_open_tenenet_request_wizard("control")

    def action_tenenet_request_followup(self, user):
        self.ensure_one()
        self.write({
            "kanban_state": "blocked",
            "tenenet_followup_user_id": user.id,
        })
        return True

    def action_tenenet_request_control(self, user):
        self.ensure_one()
        self.write({
            "kanban_state": "done",
            "tenenet_control_user_id": user.id,
        })
        return True

    @api.model
    def _ensure_tenenet_internal_helpdesk_setup(self):
        teams = self.env["helpdesk.team"].sudo().search([
            ("name", "=", self._TENENET_INTERNAL_TEAM_NAME),
        ])
        for team in teams:
            self._ensure_tenenet_internal_team_stages(team)
        self._backfill_tenenet_internal_tickets(teams)

    @api.model
    def _ensure_tenenet_internal_team_stages(self, team):
        stage_mapping = {}
        desired_stage_ids = []
        for stage in team.stage_ids.sorted(key=lambda rec: (rec.sequence, rec.id)):
            if len(stage.team_ids) == 1 and stage.team_ids == team:
                desired_stage_ids.append(stage.id)
                continue
            clone = stage.copy({
                "team_ids": [Command.set([team.id])],
            })
            stage_mapping[stage.id] = clone.id
            desired_stage_ids.append(clone.id)

        if stage_mapping:
            if team.to_stage_id and team.to_stage_id.id in stage_mapping:
                team.to_stage_id = stage_mapping[team.to_stage_id.id]
            if team.from_stage_ids:
                team.from_stage_ids = [
                    Command.set([
                        stage_mapping.get(stage.id, stage.id)
                        for stage in team.from_stage_ids
                    ])
                ]
            team.stage_ids = [Command.set(desired_stage_ids)]
            for old_stage_id, new_stage_id in stage_mapping.items():
                self.env["helpdesk.ticket"].sudo().search([
                    ("team_id", "=", team.id),
                    ("stage_id", "=", old_stage_id),
                ]).with_context(allow_handover_stage_write=True).write({
                    "stage_id": new_stage_id,
                })

        team.stage_ids.sudo().write({
            "legend_normal": _("V riešení"),
            "legend_blocked": _("Vyžaduje follow-up"),
            "legend_done": _("Vyžaduje kontrolu"),
        })

    @api.model
    def _backfill_tenenet_internal_tickets(self, teams=False):
        if not teams:
            teams = self.env["helpdesk.team"].sudo().search([
                ("name", "=", self._TENENET_INTERNAL_TEAM_NAME),
            ])
        root_user = self.env.ref("base.user_root", raise_if_not_found=False)
        admin_user = self.env.ref("base.user_admin", raise_if_not_found=False)
        protected_user_ids = {
            SUPERUSER_ID,
            *(root_user.ids),
            *(admin_user.ids),
        }
        tickets = self.sudo().search([("team_id", "in", teams.ids)])
        for ticket in tickets:
            requester = ticket.tenenet_requested_by_user_id
            if not requester:
                if ticket.create_uid and ticket.create_uid.id not in protected_user_ids:
                    requester = ticket.create_uid
                elif ticket.user_id:
                    requester = ticket.user_id
                elif ticket.create_uid:
                    requester = ticket.create_uid
            if not requester:
                raise ValidationError(
                    _("Nepodarilo sa určiť používateľa, ktorý vytvoril internú TENENET helpdesk požiadavku %s.", ticket.display_name)
                )

            vals = {}
            if ticket.tenenet_requested_by_user_id != requester:
                vals["tenenet_requested_by_user_id"] = requester.id
            if not ticket.user_id:
                vals["user_id"] = requester.id
            if vals:
                ticket.with_context(
                    allow_tenenet_requester_write=True,
                    allow_handover_stage_write=True,
                ).write(vals)
