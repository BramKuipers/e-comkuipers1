# -*- coding: utf-8 -*-

import json
import requests

from urllib import parse as urlparse

from odoo import fields, models, api, _


class ResCompany(models.Model):
    _name = 'res.company'
    _inherit = ['res.company', 'mail.thread', 'mail.activity.mixin']

    exact_online_uuid = fields.Char()
    exact_online_active = fields.Boolean()
    exact_online_state = fields.Selection([
        ('no', 'Not connected'),
        ('registered', 'Connector registered'),
        ('payment', 'Awaiting payment'),
        ('init', 'Ready for initial sync'),
        ('ok', 'Operating normally'),
        ('reconnect', 'Reconnect to connector'),
        ('error', 'Error')
    ], "Status", default='no', required=True, readonly=True)
    exact_online_state_message = fields.Text(help="Provides an explanation of the error")
    exact_online_sync_from = fields.Date(help="If filled out, the connector will start syncing accounting data "
                                              "starting from the specified date.")
    exact_online_subscription_level = fields.Selection([
        ('standard', 'Standard'),
        ('advanced', 'Advanced'),
    ], "Subscription level", default='standard', required=True, readonly=True)

    @api.model
    def get_exact_connection_params(self):
        Params = self.env['ir.config_parameter'].sudo()
        return {
            'base_url': Params.get_param('exact_online.base_url'),
            'sync': Params.get_param('exact_online.sync_path'),
            'register': Params.get_param('exact_online.registration_path'),
        }

    def get_exact_registration_params(self):
        self.ensure_one()
        Params = self.env['ir.config_parameter'].sudo()
        exact_params = self.get_exact_connection_params()
        db_name = self.env.registry.db_name
        connector_url = urlparse.urljoin(exact_params['base_url'], exact_params['register'])
        connector_url = connector_url.rstrip('/')
        odoo_url = Params.get_param('web.base.url')
        return {
            'db': db_name,
            'url': odoo_url,
            'company': self.id,
            'user': self.env.user.login,
            'country': self.country_id.code.lower(),
            'endpoint': connector_url,
        }

    def action_register_exact_online_connector(self):
        self.ensure_one()
        params = self.get_exact_registration_params()
        connector_url = params.pop('endpoint')
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '{}?{}'.format(connector_url, urlparse.urlencode(params)),
        }

    def action_reconnect_exact_online_connector(self):
        self.ensure_one()
        params = self.get_exact_registration_params()
        connector_url = params.pop('endpoint')
        params['uuid'] = self.exact_online_uuid
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '{}?{}'.format(connector_url, urlparse.urlencode(params)),
        }

    def action_do_initial_sync(self):
        self.ensure_one()
        InitSync = self.env['exact.initial_sync']
        wizard = InitSync.search([('company_id', '=', self.id)], limit=1)
        if wizard.state == 'done':
            wizard.unlink()
        if not wizard.exists():
            wizard = InitSync.create({'company_id': self.id})
        return wizard.action_reload()

    def call_exact(self, data):
        """
        Proxy method to call Exact Online with the correct parameters
        :param data: The data to send
        :type data: dict
        :return: The Response of the requests.post call to the correct endpoint
        :rtype: requests.Response
        """
        self.ensure_one()
        params = self.get_exact_connection_params()
        sync_url = urlparse.urljoin(params['base_url'], params['sync'])
        data.update({
            'uuid': self.exact_online_uuid,
        })
        return requests.post(sync_url,
                             data=json.dumps({'params': data}),
                             headers={'Content-Type': 'application/json'})

    def write(self, vals):
        res = super(ResCompany, self).write(vals)
        # Fix journals to sync when the subscription level changes.
        if 'exact_online_active' in vals or 'exact_online_subscription_level' in vals:
            AccountJournal = self.env['account.journal']
            for company in self:
                journals = AccountJournal.search([('company_id', '=', company.id)])
                journals.exact_check_subscription_level(raise_exception=False)
        return res

    def exact_schedule_activity_exact_connection_lost(self):
        # Do not spam activities, if one exists don't create another one
        users = self.env['res.users'].sudo().search([('groups_id', 'in', self.sudo().env.ref('exact_online_connector.group_exact_online_connector_manager').id)])
        activity_type = self.sudo().env.ref('exact_online_connector.mail_activity_type_exact_reconnect')
        for user in users:
            if self in user.company_ids:
                if not self.env['mail.activity'].search([
                    ('user_id', '=', user.id), ('res_model', '=', 'res.company'),
                    ('activity_type_id', '=', activity_type.id)
                ]):
                    self.activity_schedule(
                        activity_type_id=activity_type.id,
                        user_id=user.id,
                        date_deadline=fields.Date.today(),
                        summary=_("The Exact Online connector lost connection to your Exact administration.\n"
                                  "Please reconnect your connector as soon as possible from the company form!")
                    )
        return True

    def exact_schedule_activity_connection_to_odoo_lost(self):
        # Do not spam activities, if one exists don't create another one
        users = self.env['res.users'].sudo().search([('groups_id', 'in', self.sudo().env.ref('exact_online_connector.group_exact_online_connector_manager').id)])
        activity_type = self.sudo().env.ref('exact_online_connector.mail_activity_type_exact_reconnect')
        for user in users:
            if self in user.company_ids:
                if not self.env['mail.activity'].search([
                    ('user_id', '=', user.id), ('res_model', '=', 'res.company'),
                    ('activity_type_id', '=', activity_type.id)
                ]):
                    self.activity_schedule(
                        activity_type_id=activity_type.id,
                        user_id=user.id,
                        date_deadline=fields.Date.today(),
                        summary=_("The Exact Online connector lost connection to your Odoo database, did you change your credentials?\n"
                                  "Please reconnect your connector as soon as possible from the company form!")
                    )
        return True

    def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None):
        pass
