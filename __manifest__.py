{
    'name': "TENENET Projekty",

    'summary': "Riadenie projektov, alokácií a reportingu pre TENENET",

    'description': """
Odoo v19 module suite for Tenenet (Slovak NGO).
Manages projects, employee allocations, utilization tracking,
and P&L reporting by program.
    """,

    'author': "Tenenet",
    'website': "https://www.tenenet.sk",

    'category': 'Project',
    'version': '19.0.3.0.0',
    'license': 'LGPL-3',

    'depends': ['base', 'hr'],

    'data': [
        'security/tenenet_security.xml',
        'security/ir.model.access.csv',
        'data/tenenet_program_data.xml',
        'data/tenenet_donor_data.xml',
        'views/tenenet_program_views.xml',
        'views/tenenet_donor_views.xml',
        'views/tenenet_project_views.xml',
        'views/tenenet_allocation_views.xml',
        'views/tenenet_utilization_views.xml',
        'views/tenenet_pl_line_views.xml',
        'views/hr_employee_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}

