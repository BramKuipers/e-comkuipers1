# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'exact.sync.mixin']

    exact_online_code = fields.Char(company_dependent=True)
    exact_online_guid = fields.Char(company_dependent=True)
    exact_online_state = fields.Selection(company_dependent=True)

    def exact_get_company(self):
        company = super(ResPartner, self).exact_get_company()
        if not company:
            if not self.company_id:
                return self.env['res.company'].sudo().search([])
        return company

    def _increase_rank(self, field, n=1):
        """
        Since this does not trigger the ORM but is relevant for the update if the partner is a customer/supplier
        in Exact. Trigger an update if the rank was 0 before the super is called
        """
        partners_at_zero = self.filtered(lambda p: not p[field] or p[field] < 1)
        super(ResPartner, self)._increase_rank(field, n)
        if not self.env.context.get('exact_no_sync') and partners_at_zero:
            partners_at_zero.exact_create_transaction()
