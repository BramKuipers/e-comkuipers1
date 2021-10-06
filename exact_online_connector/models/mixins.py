# -*- coding: utf-8 -*-

from lxml import etree

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ExactOnlineConnectorDataMixin(models.AbstractModel):
    _name = 'exact.data.mixin'

    exact_online_code = fields.Char(help="The primary key used in Exact Online, this is usually a field name `Code`",
                                    copy=False)


class ExactOnlineSyncMixin(models.AbstractModel):
    _name = 'exact.sync.mixin'
    _inherit = 'exact.data.mixin'

    exact_online_guid = fields.Char(copy=False)
    exact_online_state = fields.Selection([
        ('no', 'Nothing to sync'),
        ('queued', 'Queued for sync'),
        ('syncing', 'Syncing'),
        ('error', 'Error'),
        ('synced', 'Synced')
    ], "Exact Online sync status", default='no', required=True, copy=False)

    @api.model
    def get_ignored_fields(self):
        # We do not automatically track updates to binary fields and fields necessary for the connector's operation
        binary_fields = [name for name, field in self._fields.items() if field.type == 'binary']
        return binary_fields + [
            'exact_online_code',
            'exact_online_guid',
            'exact_online_state',
        ]

    def exact_get_company(self):
        if self._context.get('company_id'):
            return self.env['res.company'].browse(self._context.get('company_id'))
        if self._context.get('force_company'):
            return self.env['res.company'].browse(self._context.get('force_company'))
        company = self.env.user.company_id
        if self:
            self.ensure_one()
            if 'company_id' in self._fields:
                return getattr(self, 'company_id')
            for field in self._fields:
                if self._fields[field].type == 'many2one' and self._fields[field].comodel_name == 'res.company':
                    return getattr(self, field)
        return company

    def exact_handle_create(self):
        if not self.env.context.get('exact_no_sync'):
            self.exact_create_transaction()

    def exact_handle_write(self, vals):
        if not self.env.context.get('exact_no_sync'):
            if not all(f in self.get_ignored_fields() for f in vals):
                self.exact_create_transaction()

    def exact_create_transaction(self, companies=None, initial=False):
        ExactTransaction = self.env['exact.transaction'].sudo()
        for record in self:
            r_companies = companies
            if r_companies is None:
                r_companies = record.exact_get_company()
            if not initial:
                r_companies = r_companies.filtered(lambda c: c.exact_online_active)
            if r_companies:
                ExactTransaction.create_transactions(self._name, record.id, r_companies)
                record.exact_online_state = 'queued'

    @api.model_create_multi
    def create(self, vals_list):
        records = super(ExactOnlineSyncMixin, self).create(vals_list)
        records.exact_handle_create()
        return records

    def write(self, vals):
        res = super(ExactOnlineSyncMixin, self).write(vals)
        self.exact_handle_write(vals)
        return res

    def unlink(self):
        for record in self:
            if record.exact_online_guid or record.exact_online_code:
                raise ValidationError(_(
                    '{}({}) - {}, cannot be deleted because it is synced with Exact Online.\n'
                    'Please archive this record instead!'
                ).format(record._name, record.id, record.display_name))
        return super(ExactOnlineSyncMixin, self).unlink()

    def action_view_transactions(self):
        action = self.env.ref('exact_online_connector.action_view_transactions').read()[0]
        action['domain'] = [('res_model', '=', self._name), ('res_id', 'in', self.ids)]
        action['context'] = {}
        return action

    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(ExactOnlineSyncMixin, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar,
                                                     submenu=submenu)
        if view_type == 'form':
            doc = etree.XML(res['arch'])
            button_box = doc.xpath('//div[hasclass("oe_button_box")]')
            button_xml = """
                <button type="object" name="action_view_transactions" class="oe_stat_button" readonly="1" modifiers="{&quot;readonly&quot;: true}">
                    <div class="fa fa-fw o_button_icon" style="margin-right: 6px">
                        <img src="/exact_online_connector/static/description/icon.png" style="max-width: 100%"/>
                    </div>
                    <div class="o_form_field o_stat_info">
                        <field name="exact_online_state" readonly="1" modifiers="{&quot;readonly&quot;: true}"/>
                    </div>
                </button>
                """
            if button_box:
                for node in button_box:
                    button_node = etree.fromstring(button_xml)
                    node.append(button_node)
            else:
                button_xml = """
                        <div class="oe_button_box" name="button_box">
                            {}
                        </div>
                    """.format(button_xml)
                button_node = etree.fromstring(button_xml)
                for node in doc.xpath('//sheet'):
                    node.insert(0, button_node)
                    break
            res['arch'] = etree.tostring(doc, encoding='unicode')
            res['fields'].update(self.fields_get(['exact_online_state']))
        return res
