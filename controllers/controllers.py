# from odoo import http


# class TenenetProjects(http.Controller):
#     @http.route('/tenenet_projects/tenenet_projects', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/tenenet_projects/tenenet_projects/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('tenenet_projects.listing', {
#             'root': '/tenenet_projects/tenenet_projects',
#             'objects': http.request.env['tenenet_projects.tenenet_projects'].search([]),
#         })

#     @http.route('/tenenet_projects/tenenet_projects/objects/<model("tenenet_projects.tenenet_projects"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('tenenet_projects.object', {
#             'object': obj
#         })

