from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.exceptions import AccessError, UserError, ValidationError


class TenenetHelpdeskMassTicketWizard(models.TransientModel):
    _name = "tenenet.helpdesk.mass.ticket.wizard"
    _description = "TENENET Hromadný Helpdesk Ticket"

    name = fields.Char(
        string="Predmet",
        required=True,
    )
    description = fields.Html(
        string="Popis",
    )
    team_id = fields.Many2one(
        "helpdesk.team",
        string="Helpdesk tím",
        required=True,
        default=lambda self: self.env["helpdesk.ticket"]._get_tenenet_internal_team(self.env.company),
    )
    target_type = fields.Selection(
        [
            ("company", "Celá spoločnosť"),
            ("department", "Oddelenie"),
            ("organizational_unit", "Organizačná zložka"),
            ("project", "Projekt"),
        ],
        string="Cieľ",
        required=True,
        default="department",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Spoločnosť",
        default=lambda self: self.env.company,
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Oddelenie",
    )
    organizational_unit_id = fields.Many2one(
        "tenenet.organizational.unit",
        string="Organizačná zložka",
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_employee_ids",
        string="Pridelení zamestnanci",
    )
    employee_count = fields.Integer(
        compute="_compute_employee_ids",
        string="Počet zamestnancov",
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
        required=True,
    )
    date_deadline = fields.Date(
        string="Termín",
    )

    @api.model
    def _current_user_can_create_mass_ticket(self):
        ticket_model = self.env["helpdesk.ticket"]
        return bool(
            ticket_model._user_has_tenenet_helpdesk_manager_role(self.env.user)
            or self.env.user.has_group("base.group_system")
        )

    @api.depends("target_type", "company_id", "department_id", "organizational_unit_id", "project_id")
    def _compute_employee_ids(self):
        Employee = self.env["hr.employee"].sudo()
        Assignment = self.env["tenenet.project.assignment"].sudo()
        for wizard in self:
            employees = Employee.browse()
            if wizard.target_type == "company" and wizard.company_id:
                employees = Employee.search([
                    ("active", "=", True),
                    ("company_id", "=", wizard.company_id.id),
                ])
            elif wizard.target_type == "department" and wizard.department_id:
                employees = Employee.search([
                    ("active", "=", True),
                    ("department_id", "=", wizard.department_id.id),
                ])
            elif wizard.target_type == "organizational_unit" and wizard.organizational_unit_id:
                employees = Employee.search([
                    ("active", "=", True),
                    ("organizational_unit_id", "=", wizard.organizational_unit_id.id),
                ])
            elif wizard.target_type == "project" and wizard.project_id:
                assignments = Assignment.search([
                    ("project_id", "=", wizard.project_id.id),
                    ("active", "=", True),
                ])
                employees = assignments.mapped("employee_id").filtered("active")

            wizard.employee_ids = [Command.set(employees.ids)]
            wizard.employee_count = len(employees)

    @api.constrains("team_id")
    def _check_team(self):
        ticket_model = self.env["helpdesk.ticket"]
        for wizard in self:
            if not ticket_model._is_tenenet_internal_team(wizard.team_id):
                raise ValidationError(_("Hromadný ticket je dostupný iba pre tím Interné TENENET."))

    def _check_mass_ticket_access(self):
        if not self._current_user_can_create_mass_ticket():
            raise AccessError(_("Hromadný ticket môže vytvoriť iba TENENET helpdesk manažér alebo systémový administrátor."))

    def _check_target(self):
        self.ensure_one()
        if self.target_type == "company" and not self.company_id:
            raise ValidationError(_("Vyberte spoločnosť."))
        if self.target_type == "department" and not self.department_id:
            raise ValidationError(_("Vyberte oddelenie."))
        if self.target_type == "organizational_unit" and not self.organizational_unit_id:
            raise ValidationError(_("Vyberte organizačnú zložku."))
        if self.target_type == "project" and not self.project_id:
            raise ValidationError(_("Vyberte projekt."))
        if not self.employee_ids:
            raise UserError(_("Pre vybraný cieľ sa nenašli aktívni zamestnanci."))

    def action_create_ticket(self):
        self.ensure_one()
        self._check_mass_ticket_access()
        self._check_target()

        current_user = self.env.user
        ticket = self.env["helpdesk.ticket"].sudo().with_context(
            allow_tenenet_internal_system_create=True,
        ).create({
            "name": self.name,
            "description": self.description,
            "team_id": self.team_id.id,
            "tenenet_requested_by_user_id": current_user.id,
            "user_id": current_user.id,
            "company_id": self.team_id.company_id.id or self.env.company.id,
        })
        self.env["tenenet.helpdesk.subtask"].sudo().create({
            "ticket_id": ticket.id,
            "name": self.name,
            "description": self.description,
            "employee_ids": [Command.set(self.employee_ids.ids)],
            "priority": self.priority,
            "date_deadline": self.date_deadline,
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Hromadný ticket"),
            "res_model": "helpdesk.ticket",
            "res_id": ticket.id,
            "view_mode": "form",
            "target": "current",
        }
