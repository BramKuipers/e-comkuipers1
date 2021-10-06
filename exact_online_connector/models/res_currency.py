# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class ResCurrency(models.Model):
    _name = 'res.currency'
    _inherit = ['res.currency', 'exact.data.mixin']

    exact_online_code = fields.Char("Exact Online Code", related='name')
