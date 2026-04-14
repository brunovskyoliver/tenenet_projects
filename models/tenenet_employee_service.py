from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetEmployeeService(models.Model):
    _name = "tenenet.employee.service"
    _description = "Služba zamestnanca"
    _order = "sequence, name, id"

    sequence = fields.Integer(string="Poradie", default=10)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        index=True,
    )
    service_catalog_id = fields.Many2one(
        "tenenet.service.catalog",
        string="Katalóg služby",
        ondelete="restrict",
    )
    name = fields.Char(string="Služba", required=True)
    description = fields.Text(string="Poznámka")
    delivery_online = fields.Boolean(string="Online", default=True)
    delivery_in_person = fields.Boolean(string="Osobne", default=True)
    active = fields.Boolean(string="Aktívne", default=True)
    manager_user_ids = fields.Many2many(
        "res.users",
        string="Nadriadení používatelia",
        relation="tenenet_employee_service_manager_rel",
        column1="service_id",
        column2="user_id",
        compute="_compute_manager_user_ids",
        store=True,
        readonly=True,
    )

    @api.depends("employee_id", "employee_id.service_manager_user_ids")
    def _compute_manager_user_ids(self):
        for rec in self:
            rec.manager_user_ids = rec.employee_id.service_manager_user_ids

    @api.model
    def _find_or_create_service_catalog(self, service_name):
        normalized_name = (service_name or "").strip()
        if not normalized_name:
            return self.env["tenenet.service.catalog"]

        catalog = self.env["tenenet.service.catalog"].search([("name", "=", normalized_name)], limit=1)
        if not catalog:
            catalog = self.env["tenenet.service.catalog"].create({"name": normalized_name})
        return catalog

    @api.model
    def _prepare_service_sync_vals(self, vals):
        synced_vals = dict(vals)
        if "service_catalog_id" in vals:
            catalog = self.env["tenenet.service.catalog"].browse(vals["service_catalog_id"]) if vals["service_catalog_id"] else self.env["tenenet.service.catalog"]
            synced_vals["name"] = catalog.name or False
            return synced_vals

        if "name" not in vals:
            return synced_vals

        catalog = self._find_or_create_service_catalog(vals.get("name"))
        synced_vals["name"] = catalog.name or False
        synced_vals["service_catalog_id"] = catalog.id or False
        return synced_vals

    @api.model_create_multi
    def create(self, vals_list):
        synced_vals_list = [self._prepare_service_sync_vals(vals) for vals in vals_list]
        return super().create(synced_vals_list)

    def write(self, vals):
        return super().write(self._prepare_service_sync_vals(vals))

    @api.constrains("delivery_online", "delivery_in_person")
    def _check_delivery_modes(self):
        for rec in self:
            if not rec.delivery_online and not rec.delivery_in_person:
                raise ValidationError("Služba musí byť dostupná online alebo osobne.")
