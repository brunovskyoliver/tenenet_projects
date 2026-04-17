from markupsafe import Markup, escape

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .tenenet_onboarding_task_template import PHASE_SELECTION, PHASE_SEQUENCE


PHASE_ORDER = ["pre_hire", "day_one", "first_weeks", "done"]


class TenenetOnboarding(models.Model):
    _name = "tenenet.onboarding"
    _description = "Onboarding proces"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    _HELPDESK_TEAM_NAME = "Interné TENENET"
    _HELPDESK_ONBOARDING_STAGE_NAME = "Onboarding"

    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        tracking=True,
        ondelete="set null",
    )
    candidate_name = fields.Char(
        string="Meno kandidáta",
        help="Automaticky vyplnené z mena zamestnanca. Použite pred vytvorením záznamu zamestnanca.",
    )
    job_id = fields.Many2one(
        "hr.job",
        string="Obsadzovaná pozícia",
        tracking=True,
    )
    phase = fields.Selection(
        PHASE_SELECTION + [("done", "Dokončený")],
        string="Fáza",
        default="pre_hire",
        required=True,
        tracking=True,
    )
    manager_user_id = fields.Many2one(
        "res.users",
        string="Manažér",
        tracking=True,
        help="Priamy nadriadený nového zamestnanca.",
    )
    hr_user_id = fields.Many2one(
        "res.users",
        string="HR kontakt",
        tracking=True,
    )
    operations_user_id = fields.Many2one(
        "res.users",
        string="Prevádzka",
        tracking=True,
    )
    project_manager_user_id = fields.Many2one(
        "res.users",
        string="Projektový manažér",
        tracking=True,
    )
    payroll_user_id = fields.Many2one(
        "res.users",
        string="Mzdové oddelenie",
        tracking=True,
    )
    buddy_employee_id = fields.Many2one(
        "hr.employee",
        string="Sprievodca",
        tracking=True,
        help="Skúsený kolega, ktorý pomáha nováčikovi sa začleniť.",
    )
    start_date = fields.Date(
        string="Dátum nástupu",
        tracking=True,
    )
    project_related = fields.Boolean(
        string="Projektový nástup",
        default=False,
        tracking=True,
        help="Zapnite pre onboardingy, kde zamestnanec nastupuje na projekt (Sheet 4 úlohy).",
    )
    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk požiadavka",
        readonly=True,
        copy=False,
        tracking=True,
    )
    helpdesk_ticket_stage_id = fields.Many2one(
        "helpdesk.stage",
        string="Fáza požiadavky",
        related="helpdesk_ticket_id.stage_id",
        readonly=True,
        store=True,
    )
    task_ids = fields.One2many(
        "tenenet.onboarding.task",
        "onboarding_id",
        string="Úlohy",
    )
    task_count = fields.Integer(
        string="Počet úloh",
        compute="_compute_progress",
        store=True,
    )
    task_done_count = fields.Integer(
        string="Splnené úlohy",
        compute="_compute_progress",
        store=True,
    )
    progress = fields.Float(
        string="Postup (%)",
        compute="_compute_progress",
        store=True,
    )
    note = fields.Html(string="Poznámky")

    # --------------------------------------------------------------------------
    # Computed fields
    # --------------------------------------------------------------------------

    @api.depends("employee_id", "candidate_name", "job_id")
    def _compute_name(self):
        for rec in self:
            person = rec.employee_id.name or rec.candidate_name or _("(bez mena)")
            if rec.job_id:
                rec.name = _("Onboarding - %(person)s - %(position)s", person=person, position=rec.job_id.name)
            else:
                rec.name = _("Onboarding - %s", person)

    @api.depends("task_ids.state")
    def _compute_progress(self):
        for rec in self:
            tasks = rec.task_ids
            total = len(tasks)
            done = len(tasks.filtered(lambda t: t.state in ("done", "skipped", "not_applicable")))
            rec.task_count = total
            rec.task_done_count = done
            rec.progress = (done / total * 100.0) if total else 0.0

    def _recompute_progress(self):
        self.sudo()._compute_progress()
        for rec in self:
            rec.sudo().write({
                "task_count": rec.task_count,
                "task_done_count": rec.task_done_count,
                "progress": rec.progress,
            })

    # --------------------------------------------------------------------------
    # Onchange — auto-fill from employee
    # --------------------------------------------------------------------------

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            if self.employee_id.parent_id and self.employee_id.parent_id.user_id:
                self.manager_user_id = self.employee_id.parent_id.user_id
            if self.employee_id.job_id and not self.job_id:
                self.job_id = self.employee_id.job_id
            self.candidate_name = self.employee_id.name

    # --------------------------------------------------------------------------
    # CRUD
    # --------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._generate_tasks_from_templates()
            rec._ensure_helpdesk_ticket()
        return records

    # --------------------------------------------------------------------------
    # Task generation
    # --------------------------------------------------------------------------

    def _resolve_responsible_user(self, role):
        self.ensure_one()
        mapping = {
            "manager": self.manager_user_id,
            "hr": self.hr_user_id,
            "operations": self.operations_user_id,
            "project_manager": self.project_manager_user_id,
            "payroll": self.payroll_user_id,
            "buddy": self.buddy_employee_id.user_id if self.buddy_employee_id else False,
            "cfo": False,
            "ceo": False,
            "guarantor": False,
        }
        return mapping.get(role, False)

    def _generate_tasks_from_templates(self):
        self.ensure_one()
        domain = [("active", "=", True)]
        if not self.project_related:
            domain.append(("project_only", "=", False))
        templates = self.env["tenenet.onboarding.task.template"].search(domain)
        task_vals = []
        for tmpl in templates:
            responsible = self._resolve_responsible_user(tmpl.responsible_role)
            task_vals.append({
                "onboarding_id": self.id,
                "name": tmpl.name,
                "phase": tmpl.phase,
                "phase_sequence": PHASE_SEQUENCE.get(tmpl.phase, 99),
                "sequence": tmpl.sequence,
                "responsible_role": tmpl.responsible_role,
                "responsible_user_id": responsible.id if responsible else False,
                "is_mandatory": tmpl.is_mandatory,
                "template_id": tmpl.id,
                "state": "todo",
            })
        self.env["tenenet.onboarding.task"].create(task_vals)

    def action_regenerate_tasks(self):
        """Regenerate tasks from templates (manager only). Keeps done tasks."""
        self.ensure_one()
        ticket_model = self.env["helpdesk.ticket"]
        if not ticket_model._user_has_tenenet_helpdesk_manager_role(self.env.user) and not self.env.is_superuser():
            raise UserError(_("Regenerovanie úloh môže robiť iba TENENET helpdesk manažér."))
        existing_template_ids = self.task_ids.mapped("template_id").ids
        domain = [("active", "=", True), ("id", "not in", existing_template_ids)]
        if not self.project_related:
            domain.append(("project_only", "=", False))
        new_templates = self.env["tenenet.onboarding.task.template"].search(domain)
        task_vals = []
        for tmpl in new_templates:
            responsible = self._resolve_responsible_user(tmpl.responsible_role)
            task_vals.append({
                "onboarding_id": self.id,
                "name": tmpl.name,
                "phase": tmpl.phase,
                "phase_sequence": PHASE_SEQUENCE.get(tmpl.phase, 99),
                "sequence": tmpl.sequence,
                "responsible_role": tmpl.responsible_role,
                "responsible_user_id": responsible.id if responsible else False,
                "is_mandatory": tmpl.is_mandatory,
                "template_id": tmpl.id,
                "state": "todo",
            })
        if task_vals:
            self.env["tenenet.onboarding.task"].create(task_vals)

    # --------------------------------------------------------------------------
    # Phase transitions
    # --------------------------------------------------------------------------

    def action_next_phase(self):
        self.ensure_one()
        if self.phase == "done":
            raise UserError(_("Onboarding je už dokončený."))
        current_index = PHASE_ORDER.index(self.phase)
        next_phase = PHASE_ORDER[current_index + 1]
        self._validate_phase_completion(self.phase)
        self.write({"phase": next_phase})
        if next_phase == "done":
            self._close_helpdesk_ticket()
        return True

    def action_previous_phase(self):
        self.ensure_one()
        ticket_model = self.env["helpdesk.ticket"]
        if not (
            ticket_model._user_has_tenenet_helpdesk_editor_role(self.env.user)
            or self.env.is_superuser()
        ):
            raise UserError(_("Späť môže ísť iba TENENET helpdesk editor alebo manažér."))
        if self.phase == "pre_hire":
            raise UserError(_("Toto je prvá fáza, nie je kam sa vrátiť."))
        current_index = PHASE_ORDER.index(self.phase)
        self.write({"phase": PHASE_ORDER[current_index - 1]})
        return True

    def action_complete(self):
        self.ensure_one()
        self._validate_phase_completion(self.phase)
        self.write({"phase": "done"})
        self._close_helpdesk_ticket()
        return True

    def _validate_phase_completion(self, phase):
        self.ensure_one()
        if phase == "done":
            return
        mandatory_incomplete = self.task_ids.filtered(
            lambda t: t.phase == phase and t.is_mandatory and t.state == "todo"
        )
        if mandatory_incomplete:
            raise ValidationError(_(
                "Pred pokračovaním je potrebné splniť všetky povinné úlohy v aktuálnej fáze.\n"
                "Nesplnené povinné úlohy:\n%s",
                "\n".join("- " + t.name for t in mandatory_incomplete)
            ))

    # --------------------------------------------------------------------------
    # Helpdesk integration
    # --------------------------------------------------------------------------

    def _ensure_helpdesk_ticket(self):
        self.ensure_one()
        if self.helpdesk_ticket_id:
            return self.helpdesk_ticket_id
        team = self._get_helpdesk_team()
        if not team:
            return False
        stage = self._get_or_create_onboarding_stage(team)
        requester_user = self._get_helpdesk_requester_user(team)
        assignee = self._get_helpdesk_ticket_assignee(team, requester_user=requester_user)
        if not assignee:
            return False
        ticket_vals = {
            "name": self.name,
            "team_id": team.id,
            "stage_id": stage.id,
            "description": self._build_helpdesk_ticket_description(),
            "tenenet_requested_by_user_id": requester_user.id,
            "user_id": assignee.id,
            "tenenet_onboarding_id": self.id,
        }
        ticket = self.env["helpdesk.ticket"].with_context(
            default_team_id=team.id,
            tenenet_requested_by_user_id=requester_user.id,
            allow_tenenet_internal_system_create=True,
        ).sudo().create(ticket_vals)
        self.helpdesk_ticket_id = ticket.id
        self.message_post(body=_("Bola vytvorená helpdesk požiadavka %s.", ticket._get_html_link()))
        return ticket

    def _get_helpdesk_team(self):
        self.ensure_one()
        for domain in [
            [("name", "=", self._HELPDESK_TEAM_NAME)],
        ]:
            team = self.env["helpdesk.team"].sudo().search(domain, limit=1, order="id desc")
            if team:
                return team
        return False

    def _get_or_create_onboarding_stage(self, team):
        self.ensure_one()
        stage = team.stage_ids.filtered(lambda s: s.name == self._HELPDESK_ONBOARDING_STAGE_NAME)[:1]
        if stage:
            return stage
        close_stage = team.to_stage_id or team.stage_ids.filtered("fold")[:1]
        sequence = max((close_stage.sequence - 1) if close_stage else 10, 1)
        return self.env["helpdesk.stage"].sudo().create({
            "name": self._HELPDESK_ONBOARDING_STAGE_NAME,
            "sequence": sequence,
            "fold": False,
            "team_ids": [Command.link(team.id)],
        })

    def _build_helpdesk_ticket_description(self):
        self.ensure_one()
        person = self.employee_id.name or self.candidate_name or ""
        position = self.job_id.name or ""
        start = self.start_date or ""
        return Markup("<p>%s</p><ul><li>%s</li><li>%s</li><li>%s</li></ul><p>%s</p>") % (
            escape(_("Onboarding procesu zamestnanca:")),
            escape(_("Zamestnanec: %s", person)),
            escape(_("Pozícia: %s", position)),
            escape(_("Dátum nástupu: %s", start)),
            escape(_("Požiadavka sa uzatvorí automaticky po dokončení onboarding procesu.")),
        )

    def _get_helpdesk_requester_user(self, team):
        self.ensure_one()
        candidates = (
            self.hr_user_id
            | self.env.user
            | self.create_uid
            | team.with_context(active_test=False).member_ids.filtered("active")
        )
        admin_user = self.env.ref("base.user_admin", raise_if_not_found=False)
        if admin_user:
            candidates |= admin_user
        return candidates.filtered(lambda u: u.active and not u.share)[:1]

    def _get_helpdesk_ticket_assignee(self, team, requester_user=None):
        self.ensure_one()
        requester_user = requester_user or self._get_helpdesk_requester_user(team)
        ticket_model = self.env["helpdesk.ticket"]
        if requester_user.active and ticket_model._user_has_tenenet_helpdesk_role(requester_user):
            return requester_user
        allowed_users = ticket_model._get_tenenet_allowed_assignment_users_for_user(
            requester_user, team=team,
        )
        if allowed_users:
            return allowed_users[:1]
        team_member = team.member_ids.filtered(
            lambda u: u.active and ticket_model._user_has_tenenet_helpdesk_role(u)
        )[:1]
        return team_member or team.member_ids.filtered("active")[:1] or self.env["res.users"]

    def _close_helpdesk_ticket(self):
        self.ensure_one()
        if not self.helpdesk_ticket_id:
            return
        close_stage = (
            self.helpdesk_ticket_id.team_id.to_stage_id
            or self.helpdesk_ticket_id.team_id.stage_ids.filtered("fold")[:1]
        )
        if not close_stage:
            return
        self.helpdesk_ticket_id.with_context(allow_onboarding_stage_write=True).sudo().write({
            "stage_id": close_stage.id,
        })
        self.helpdesk_ticket_id.message_post(
            body=_("Požiadavka bola automaticky uzatvorená po dokončení onboarding procesu.")
        )

    # --------------------------------------------------------------------------
    # Actions
    # --------------------------------------------------------------------------

    def action_open_helpdesk_ticket(self):
        self.ensure_one()
        if not self.helpdesk_ticket_id:
            raise UserError(_("Pre tento onboarding ešte nebola vytvorená helpdesk požiadavka."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Helpdesk požiadavka"),
            "res_model": "helpdesk.ticket",
            "view_mode": "form",
            "res_id": self.helpdesk_ticket_id.id,
            "target": "current",
        }

    def action_open_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Úlohy onboardingu"),
            "res_model": "tenenet.onboarding.task",
            "view_mode": "list,form",
            "domain": [("onboarding_id", "=", self.id)],
            "context": {"default_onboarding_id": self.id},
        }

    # --------------------------------------------------------------------------
    # Setup (called from post_init_hook)
    # --------------------------------------------------------------------------

    @api.model
    def _ensure_onboarding_helpdesk_stage(self):
        """Ensure Onboarding stage exists in every Interné TENENET team."""
        teams = self.env["helpdesk.team"].sudo().search([
            ("name", "=", self._HELPDESK_TEAM_NAME),
        ])
        for team in teams:
            stage = team.stage_ids.filtered(
                lambda s: s.name == self._HELPDESK_ONBOARDING_STAGE_NAME
            )[:1]
            if not stage:
                close_stage = team.to_stage_id or team.stage_ids.filtered("fold")[:1]
                sequence = max((close_stage.sequence - 1) if close_stage else 10, 1)
                self.env["helpdesk.stage"].sudo().create({
                    "name": self._HELPDESK_ONBOARDING_STAGE_NAME,
                    "sequence": sequence,
                    "fold": False,
                    "team_ids": [Command.link(team.id)],
                })
