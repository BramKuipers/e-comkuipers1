# -*- coding: utf-8 -*-

import datetime
import json
import requests

from odoo import fields, models, api, _


class ExactOnlineTransaction(models.Model):
    _name = 'exact.transaction'
    _description = "Transaction to Exact Online"
    _order = 'date_planned desc'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.company_id, required=True,
                                 index=True, auto_join=True)
    date_planned = fields.Datetime("Planned for", default=lambda self: fields.Datetime.now(), readonly=True)
    date_sent = fields.Datetime("Sent at", readonly=True)
    date_done = fields.Datetime("Synced at", readonly=True)
    retry_attempt = fields.Integer("Retry attempt #", readonly=True)
    res_model = fields.Char("Model",  readonly=True, required=True, states={
        'todo': [('readonly', False)],
        'retry': [('readonly', False)]
    })  # Odoo model name or special name for custom behaviour
    res_id = fields.Integer("Record ID", readonly=True, states={
        'todo': [('readonly', False)],
        'retry': [('readonly', False)]
    })
    state = fields.Selection([
        ('todo', 'To Do'),                              # Queued
        ('retry', 'Retrying'),                          # Auto queued, something went wrong in previous attempt
        ('syncing', 'Syncing'),                         # Currently the data is syncing
        ('except_odoo', 'Exception @ Odoo'),            # Problem with getting date from/inserting data into Odoo
        ('except_exact', 'Exception @ Exact'),          # Problem with getting data from/inserting data into Exact
        ('except_connector', 'Exception @ Connector'),  # Problem with or in Connector
        ('done', 'Synced')                              # Triggered externally
    ], string="Status", default='todo', readonly=True, required=True)
    exception = fields.Text(readonly=True)

    @api.model
    def create_transactions(self, res_model, res_id, companies=None):
        # If no specific companies are supplied, we create a transaction for every company
        # that has the connector enabled
        if not companies:
            companies = self.env['res.company'].search([('exact_online_active', '=', True),
                                                        ('exact_online_uuid', '!=', False)])
        result = self.env['exact.transaction']
        for company in companies:
            if not self.search_count([
                ('company_id', '=', company.id), ('state', 'in', ['todo']),
                ('res_model', '=', res_model), ('res_id', '=', res_id)
            ]):
                result |= self.create([{'company_id': company.id, 'res_model': res_model, 'res_id': res_id}])
        return result

    def name_get(self):
        return [(t.id, '{}({}) ({})'.format(t.res_model, t.res_id, t.company_id.name)) for t in self]

    def run(self):
        for transaction in self:
            if transaction.state not in ['todo', 'retry']:
                continue
            if not transaction._get_record().exists():
                transaction.write({
                    'state': 'except_odoo',
                    'exception': _("Record no longer exists in Odoo"),
                })
                continue
            params = {
                'model': transaction.res_model,
                'id': transaction.res_id,
                'transaction': transaction.id,
            }
            transaction.date_sent = fields.Datetime.now()
            response = transaction.company_id.call_exact(params)
            transaction.handle_response(response)
            self.env.cr.commit()

    def handle_response(self, response):
        """
        :param response: The response received from a call to Exact Online
        :type response: requests.Response
        """
        # Success
        if response.status_code == 200:
            result = json.loads(response.text)
            if result and 'result' in result:
                result = result['result']
            if not result.get('success', False):
                if result.get('error') == 'credentials':
                    # Connection to Database was lost we cannot process any transactions until this is fixed
                    self.company_id.exact_online_state = 'reconnect'
                    self.company_id.exact_online_active = False
                    self.company_id.exact_schedule_activity_connection_to_odoo_lost()
                    return
                self.state = 'except_connector'
                self.exception = result.get('message', _("Something went wrong while trying to process the change"))
            else:
                self.exception = ''
                self.state = 'syncing'
        # Retry-able automatic
        elif response.status_code in [502, 503, 504]:
            self.retry_attempt += 1
            if self.retry_attempt < 5:
                self.date_planned = datetime.datetime.now() + datetime.timedelta(minutes=3 * self.retry_attempt)
                self.state = 'retry'
                self.exception = _("The connector is temporarily offline, "
                                   "will try to reach the connector again in {} minutes").format(3 * self.retry_attempt)
            else:
                self.state = 'except_connector'
                self.exception = _("Too many failed attempts at automatically retrying this transaction.\n"
                                   "The connector seems to be offline, "
                                   "please contact Callista (https://callista.be/page/contact) for assistance")
        # Failure, retry-able manual
        else:
            self.retry_attempt += 1
            self.state = 'except_connector'
            self.exception = response.text
        self.action_update_record_state()

    def _get_record(self):
        self.ensure_one()
        return self.env[self.res_model].browse(self.res_id)

    def _get_mapped_state(self):
        self.ensure_one()
        if self.state in ['todo', 'retry']:
            return 'queued'
        if self.state in ['syncing']:
            return 'syncing'
        if self.state in ['done']:
            return 'synced'
        return 'error'

    def action_retry(self):
        self.write({
            'state': 'retry',
            'date_planned': fields.Datetime.now(),
        })

    def action_run(self):
        self.sudo().run()

    def action_update_record_state(self):
        for transaction in self:
            record = transaction._get_record()
            record.exact_online_state = transaction._get_mapped_state()

    def post_master_run(self):
        self.action_update_record_state()
        return True

    @api.model
    def _cron_run(self):
        now = fields.Datetime.now()
        todo = self.search([('company_id.exact_online_active', '=', True), ('date_planned', '<=', now),
                            ('state', 'in', ['todo', 'retry'])], order='date_planned asc')
        todo.run()

    def unlink(self):
        for transaction in self:
            record = self._get_record()
            if self.search_count([
                ('company_id', '=', transaction.company_id.id), ('state', 'in', ['todo', 'retry', 'syncing']),
                ('res_model', '=', transaction.res_model), ('res_id', '=', transaction.res_id),
                ('id', 'not in', self.ids)
            ]) == 0:
                record.exact_online_state = 'no' if not record.exact_online_code else 'synced'
        return super(ExactOnlineTransaction, self).unlink()
