# from odoo import models, fields, api


# class TenenetProjects(models.Model):
#     _name = 'tenenet_projects.tenenet_projects'
#     _description = 'tenenet_projects.tenenet_projects'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

