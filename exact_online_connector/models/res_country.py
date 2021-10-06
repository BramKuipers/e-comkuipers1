# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class ResCountry(models.Model):
    _name = 'res.country'
    _inherit = ['res.country', 'exact.data.mixin']

    exact_online_code = fields.Char(compute='_compute_exact_online_code', store=True)

    @api.depends('code')
    def _compute_exact_online_code(self):
        for country in self:
            country.exact_online_code = country.code.upper()
