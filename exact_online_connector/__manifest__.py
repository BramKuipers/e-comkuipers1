# -*- coding: utf-8 -*-

{
    'name': 'Exact Online Connector',
    'version': '1.0.1',
    'summary': 'Sync Exact Online with Odoo',
    'description': """
    """,
    'category': '',
    'author': 'Callista',
    'website': 'https://www.callista.be',
    'depends': [
        'account',
    ],
    'data': [
        'data/cron_data.xml',
        'data/ir_config_parameter_data.xml',
        'data/mail_activity_data.xml',

        'security/connector_security.xml',
        'security/ir.model.access.csv',

        'wizard/exact_initial_sync_view.xml',

        'views/account_view.xml',
        'views/res_company_view.xml',
        'views/res_partner_view.xml',
        'views/transaction_view.xml',
    ],
    'demo': [

    ],
    'qweb': [

    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
