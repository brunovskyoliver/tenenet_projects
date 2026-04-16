import base64
from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import email_normalize


class TenenetEmployeeAssetHandover(models.Model):
    _name = "tenenet.employee.asset.handover"
    _description = "Preberací protokol firemného majetku"
    _inherit = ["mail.thread"]
    _order = "handover_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Spoločnosť",
        related="employee_id.company_id",
        readonly=True,
        store=True,
    )
    handover_date = fields.Date(
        string="Termín odovzdania",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    asset_ids = fields.One2many(
        "tenenet.employee.asset",
        "handover_id",
        string="Majetok",
    )
    asset_count = fields.Integer(
        string="Počet položiek",
        compute="_compute_asset_count",
    )
    note = fields.Text(string="Poznámka")
    sign_template_id = fields.Many2one(
        "sign.template",
        string="Podpisová šablóna",
        readonly=True,
        copy=False,
    )
    sign_request_id = fields.Many2one(
        "sign.request",
        string="Podpisová žiadosť",
        readonly=True,
        copy=False,
        tracking=True,
    )
    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Helpdesk požiadavka",
        readonly=True,
        copy=False,
        tracking=True,
    )
    sign_state = fields.Selection(
        related="sign_request_id.state",
        string="Stav podpisu",
        readonly=True,
        store=True,
    )
    helpdesk_ticket_stage_id = fields.Many2one(
        "helpdesk.stage",
        string="Fáza požiadavky",
        related="helpdesk_ticket_id.stage_id",
        readonly=True,
        store=True,
    )

    _HELPDESK_TEAM_NAME = "Interné TENENET"
    _HELPDESK_HANDOVER_STAGE_NAME = "Preberací protokol"

    @api.depends("employee_id", "handover_date")
    def _compute_name(self):
        for rec in self:
            if rec.employee_id and rec.handover_date:
                rec.name = _("Preberací protokol - %(employee)s - %(date)s", employee=rec.employee_id.name, date=rec.handover_date)
            elif rec.employee_id:
                rec.name = _("Preberací protokol - %s", rec.employee_id.name)
            else:
                rec.name = _("Preberací protokol")

    @api.depends("asset_ids")
    def _compute_asset_count(self):
        for rec in self:
            rec.asset_count = len(rec.asset_ids)

    def action_print_protocol(self):
        self.ensure_one()
        return self.env.ref("tenenet_projects.action_report_employee_asset_handover").report_action(self)

    def action_open_sign_request(self):
        self.ensure_one()
        if not self.sign_request_id:
            raise UserError(_("Pre tento protokol ešte nebola vytvorená podpisová žiadosť."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Podpisová žiadosť"),
            "res_model": "sign.request",
            "view_mode": "kanban,list,form",
            "domain": [("id", "=", self.sign_request_id.id)],
            "context": {"create": False},
        }

    def action_open_helpdesk_ticket(self):
        self.ensure_one()
        if not self.helpdesk_ticket_id:
            raise UserError(_("Pre tento protokol ešte nebola vytvorená helpdesk požiadavka."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Helpdesk požiadavka"),
            "res_model": "helpdesk.ticket",
            "view_mode": "form",
            "res_id": self.helpdesk_ticket_id.id,
            "target": "current",
        }

    def action_send_for_signature(self, message=False):
        for handover in self:
            handover._create_sign_request(message=message)
            handover._ensure_helpdesk_ticket()
        return True

    def _create_sign_request(self, message=False):
        self.ensure_one()
        if self.sign_request_id:
            return self.sign_request_id
        if not self.asset_ids:
            raise UserError(_("Preberací protokol musí obsahovať aspoň jednu položku majetku."))

        partner = self._get_employee_sign_partner()
        template = self._create_sign_template()
        validity = False
        if template.signature_request_validity:
            validity = fields.Date.context_today(self) + relativedelta(days=template.signature_request_validity)

        sign_request = self.env["sign.request"].sudo().create({
            "template_id": template.id,
            "request_item_ids": [Command.create({
                "partner_id": partner.id,
                "role_id": self.env.ref("sign.sign_item_role_default").id,
            })],
            "reference": self.name,
            "subject": _("Preberací protokol firemného majetku"),
            "message": message or _(
                "<p>Dobrý deň,</p><p>prosíme o podpis preberacieho protokolu k odovzdanému firemnému majetku.</p>"
            ),
            "validity": validity,
            "reference_doc": f"{self._name},{self.id}",
        })
        self.write({
            "sign_template_id": template.id,
            "sign_request_id": sign_request.id,
        })
        self.message_post(body=_("Podpisová žiadosť bola odoslaná zamestnancovi %s.", partner.display_name))
        return sign_request

    def _ensure_helpdesk_ticket(self):
        self.ensure_one()
        if self.helpdesk_ticket_id:
            return self.helpdesk_ticket_id
        if not self.sign_request_id:
            raise UserError(_("Najskôr je potrebné vytvoriť podpisovú žiadosť."))

        team = self._get_helpdesk_team()
        stage = self._get_or_create_helpdesk_handover_stage(team)
        partner = self._get_employee_sign_partner()
        requester_user = self._get_helpdesk_requester_user(team)
        assignee = self._get_helpdesk_ticket_assignee(team, requester_user=requester_user)
        if not assignee and requester_user.active:
            assignee = requester_user
        if not assignee:
            assignee = team.member_ids.filtered("active")[:1]
        ticket_vals = {
            "name": self.name,
            "team_id": team.id,
            "stage_id": stage.id,
            "partner_id": partner.id,
            "partner_name": self.employee_id.name,
            "partner_email": partner.email or self.employee_id.work_email,
            "description": self._build_helpdesk_ticket_description(),
            "tenenet_requested_by_user_id": requester_user.id,
        }
        if not assignee:
            raise UserError(
                _(
                    "Pre internú TENENET helpdesk požiadavku sa nepodarilo nájsť povoleného riešiteľa. "
                    "Pridajte sebe alebo svojmu nadriadenému rolu TENENET helpdesk."
                )
            )
        ticket_vals["user_id"] = assignee.id
        ticket = self.env["helpdesk.ticket"].with_context(
            default_team_id=team.id,
            tenenet_requested_by_user_id=requester_user.id,
            allow_tenenet_internal_system_create=True,
        ).sudo().create(ticket_vals)
        self.helpdesk_ticket_id = ticket.id
        ticket.message_post(body=self._build_helpdesk_ticket_message())
        self.message_post(body=_("Bola vytvorená helpdesk požiadavka %s.", ticket._get_html_link()))
        return ticket

    def _get_helpdesk_team(self):
        self.ensure_one()
        team = self.env["helpdesk.team"].sudo().search([
            ("name", "=", self._HELPDESK_TEAM_NAME),
            ("company_id", "=", self.company_id.id),
            ("member_ids", "in", self.env.user.id),
        ], limit=1, order="id desc")
        if not team:
            team = self.env["helpdesk.team"].sudo().search([
            ("name", "=", self._HELPDESK_TEAM_NAME),
            ("company_id", "=", self.company_id.id),
            ], limit=1, order="id desc")
        if not team:
            team = self.env["helpdesk.team"].sudo().search([
                ("name", "=", self._HELPDESK_TEAM_NAME),
                ("member_ids", "in", self.env.user.id),
            ], limit=1, order="id desc")
        if not team:
            team = self.env["helpdesk.team"].sudo().search([
                ("name", "=", self._HELPDESK_TEAM_NAME),
            ], limit=1, order="id desc")
        if not team:
            raise UserError(_(
                "Nepodarilo sa nájsť helpdesk tím '%s'.",
                self._HELPDESK_TEAM_NAME,
            ))
        return team

    def _get_or_create_helpdesk_handover_stage(self, team):
        self.ensure_one()
        stage = team.stage_ids.filtered(lambda rec: rec.name == self._HELPDESK_HANDOVER_STAGE_NAME)[:1]
        if stage:
            return stage

        close_stage = team.to_stage_id or team.stage_ids.filtered("fold")[:1]
        sequence = max((close_stage.sequence - 1) if close_stage else 10, 1)
        return self.env["helpdesk.stage"].sudo().create({
            "name": self._HELPDESK_HANDOVER_STAGE_NAME,
            "sequence": sequence,
            "fold": False,
            "team_ids": [Command.link(team.id)],
        })

    def _build_helpdesk_ticket_description(self):
        self.ensure_one()
        sign_url = escape(self._get_sign_url())
        return Markup(
            "<p>%s</p><p><a href=\"%s\" target=\"_blank\">%s</a></p><p>%s</p>"
        ) % (
            escape(_("Zamestnanec má podpísať preberací protokol firemného majetku.")),
            sign_url,
            escape(_("Otvoriť dokument na podpis")),
            escape(_("Požiadavka sa uzatvorí automaticky po podpise dokumentu zamestnancom.")),
        )

    def _build_helpdesk_ticket_message(self):
        self.ensure_one()
        sign_url = escape(self._get_sign_url())
        return Markup("<p>%s</p><p><a href=\"%s\" target=\"_blank\">%s</a></p>") % (
            escape(_("Odkaz na podpis pre zamestnanca:")),
            sign_url,
            escape(_("Podpísať preberací protokol")),
        )

    def _get_sign_url(self):
        self.ensure_one()
        if not self.sign_request_id or not self.sign_request_id.request_item_ids:
            raise UserError(_("Pre tento protokol ešte nebola vytvorená podpisová žiadosť."))
        request_item = self.sign_request_id.request_item_ids[:1].sudo()
        return "%s/sign/document/%s/%s" % (
            self.get_base_url(),
            self.sign_request_id.id,
            request_item.access_token,
        )

    def _close_helpdesk_ticket_if_signed(self):
        for handover in self.filtered(lambda rec: rec.helpdesk_ticket_id and rec.sign_state == "signed"):
            close_stage = handover.helpdesk_ticket_id.team_id.to_stage_id or handover.helpdesk_ticket_id.team_id.stage_ids.filtered("fold")[:1]
            if not close_stage:
                continue
            handover.helpdesk_ticket_id.with_context(allow_handover_stage_write=True).sudo().write({
                "stage_id": close_stage.id,
            })
            handover.helpdesk_ticket_id.message_post(
                body=_("Požiadavka bola automaticky uzatvorená po podpise preberacieho protokolu.")
            )

    def _get_helpdesk_requester_user(self, team):
        self.ensure_one()
        candidate_users = (
            self.env.user
            | self.create_uid
            | self.write_uid
            | team.with_context(active_test=False).member_ids.filtered("active")
        )
        admin_user = self.env.ref("base.user_admin", raise_if_not_found=False)
        if admin_user:
            candidate_users |= admin_user
        return candidate_users.filtered(lambda user: user.active and not user.share)[:1]

    def _get_helpdesk_ticket_assignee(self, team, requester_user=None):
        self.ensure_one()
        requester_user = requester_user or self._get_helpdesk_requester_user(team)
        helpdesk_ticket_model = self.env["helpdesk.ticket"]
        if (
            requester_user.active
            and helpdesk_ticket_model._user_has_tenenet_helpdesk_role(requester_user)
        ):
            return requester_user
        allowed_users = helpdesk_ticket_model._get_tenenet_allowed_assignment_users_for_user(
            requester_user,
            team=team,
        )
        employees = self.env["hr.employee"].sudo().search([
            ("user_id", "=", requester_user.id),
        ])
        direct_managers = employees.mapped("parent_id.user_id")
        grand_managers = employees.mapped("parent_id.parent_id.user_id")
        for candidate in direct_managers | grand_managers:
            if candidate in allowed_users:
                return candidate
        team_helpdesk_member = team.member_ids.filtered(
            lambda user: user.active and helpdesk_ticket_model._user_has_tenenet_helpdesk_role(user)
        )[:1]
        if team_helpdesk_member:
            return team_helpdesk_member
        return team.member_ids.filtered("active")[:1] or self.env["res.users"]

    def _get_employee_sign_partner(self):
        self.ensure_one()
        email = (self.employee_id.work_email or "").strip()
        normalized_email = email_normalize(email)
        if not normalized_email:
            raise UserError(_("Zamestnanec %s nemá vyplnený platný pracovný email.", self.employee_id.name))

        candidate_partners = self.employee_id.work_contact_id | self.employee_id.user_id.partner_id
        partner = candidate_partners.filtered(lambda rec: rec.email_normalized == normalized_email)[:1]
        if partner:
            return partner

        partner = self.env["res.partner"].search([("email_normalized", "=", normalized_email)], limit=1)
        if partner:
            return partner

        return self.env["res.partner"].create({
            "name": self.employee_id.name,
            "email": email,
        })

    def _create_sign_template(self):
        self.ensure_one()
        pdf_datas = self._render_pdf_for_sign()
        template_vals = self.env["sign.template"].sudo().create_from_attachment_data([{
            "name": "%s.pdf" % self.name,
            "datas": pdf_datas,
        }], active=True)
        template = self.env["sign.template"].sudo().browse(template_vals["id"])
        document = template.document_ids[:1]
        if not document:
            raise UserError(_("Nepodarilo sa vytvoriť podpisový dokument."))

        self.env["sign.item"].sudo().create({
            "document_id": document.id,
            "type_id": self.env.ref("sign.sign_item_type_signature").id,
            "responsible_id": self.env.ref("sign.sign_item_role_default").id,
            "name": _("Podpis zamestnanca"),
            "page": max(document.num_pages, 1),
            "posX": 0.645,
            "posY": 0.475,
            "width": 0.255,
            "height": 0.060,
        })
        return template

    def _render_pdf_for_sign(self):
        self.ensure_one()
        pdf_content, _report_type = self.env["ir.actions.report"].sudo().with_context(
            force_report_rendering=True,
            report_pdf_no_attachment=True,
        )._render_qweb_pdf(
            "tenenet_projects.action_report_employee_asset_handover",
            self.id,
        )
        return base64.b64encode(pdf_content)
