import base64
from dateutil.relativedelta import relativedelta

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
    sign_state = fields.Selection(
        related="sign_request_id.state",
        string="Stav podpisu",
        readonly=True,
        store=True,
    )

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

    def action_send_for_signature(self, message=False):
        for handover in self:
            handover._create_sign_request(message=message)
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
            "posX": 0.620,
            "posY": 0.565,
            "width": 0.260,
            "height": 0.070,
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
