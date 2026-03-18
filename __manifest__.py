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
    'version': '19.0.4.0.0',
    'license': 'LGPL-3',

    'depends': ['base', 'hr', 'hr_holidays', 'account_reports'],

    'assets': {
        'web.assets_backend': [
            'tenenet_projects/static/src/js/tenenet_project_yearly_labor_report_filters.js',
            'tenenet_projects/static/src/js/tenenet_utilization_report_filters.js',
            'tenenet_projects/static/src/js/tenenet_allocation_report_filters.js',
            'tenenet_projects/static/src/js/tenenet_my_timesheets_action.js',
            'tenenet_projects/static/src/js/timesheet_matrix_host.js',
            'tenenet_projects/static/src/xml/tenenet_project_yearly_labor_report_filters.xml',
            'tenenet_projects/static/src/xml/tenenet_utilization_report_filters.xml',
            'tenenet_projects/static/src/xml/tenenet_allocation_report_filters.xml',
            'tenenet_projects/static/src/xml/tenenet_my_timesheets_action.xml',
            'tenenet_projects/static/src/scss/tenenet_project_yearly_labor_report.scss',
            'tenenet_projects/static/src/scss/tenenet_utilization_report.scss',
            'tenenet_projects/static/src/scss/tenenet_allocation_report.scss',
            'tenenet_projects/static/src/scss/timesheet_matrix.scss',
        ],
    },

    'data': [
        'security/tenenet_security.xml',
        'security/ir.model.access.csv',
        'data/tenenet_program_data.xml',
        'data/tenenet_donor_data.xml',
        'data/hr_leave_type_data.xml',
        'views/tenenet_program_views.xml',
        'views/tenenet_donor_views.xml',
        'views/tenenet_project_views.xml',
        'views/tenenet_allocation_views.xml',
        'views/tenenet_utilization_views.xml',
        'views/tenenet_project_yearly_labor_report_views.xml',
        'views/tenenet_allocation_report_views.xml',
        'views/tenenet_utilization_report_views.xml',
        'views/tenenet_utilization_sync_wizard_views.xml',
        'views/tenenet_pl_line_views.xml',
        'views/tenenet_project_assignment_views.xml',
        'views/tenenet_project_timesheet_views.xml',
        'views/tenenet_project_timesheet_matrix_views.xml',
        'views/tenenet_employee_tenenet_cost_views.xml',
        'views/tenenet_company_expense_views.xml',
        'views/hr_employee_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
}
