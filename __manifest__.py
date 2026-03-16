{
    'name': "Tenenet Projects",

    'summary': "Project management, employee allocation & reporting for Tenenet",

    'description': """
Odoo v19 module suite for Tenenet (Slovak NGO).
Manages projects, employee allocations, utilization tracking,
and P&L reporting by program.
    """,

    'author': "Tenenet",
    'website': "https://www.tenenet.sk",

    'category': 'Project',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',

    'depends': ['base'],

    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}

