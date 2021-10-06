# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class AccountAccount(models.Model):
    _name = 'account.account'
    _inherit = ['account.account', 'exact.data.mixin']

    exact_online_code = fields.Char("Exact Online Code", related='code')


class AccountJournal(models.Model):
    _name = 'account.journal'
    _inherit = ['account.journal', 'exact.data.mixin']

    sync_with_exact_online = fields.Boolean("Sync moves to Exact Online",
                                            help="Send all moves posted in this journal to Exact Online")
    sync_with_exact_online_available = fields.Boolean(compute='_compute_sync_availability')
    sync_from_exact_online = fields.Boolean("Sync moves from Exact Online",
                                            help="Get all moves posted in Exact Online")
    sync_from_exact_online_available = fields.Boolean(compute='_compute_sync_availability')
    last_sync_from_exact_online = fields.Datetime(readonly=True)

    @api.depends('type', 'company_id.exact_online_subscription_level')
    def _compute_sync_availability(self):
        for journal in self:
            if journal.type == 'bank':
                journal.sync_with_exact_online_available = False
            elif journal.company_id.exact_online_subscription_level == 'standard':
                journal.sync_with_exact_online_available = journal.type in ['sale', 'purchase']
            else:
                journal.sync_with_exact_online_available = True
            journal.sync_from_exact_online_available = journal.company_id.exact_online_subscription_level == 'advanced'

    @api.constrains('sync_with_exact_online', 'sync_from_exact_online', 'exact_online_code')
    def _check_no_both_way_sync(self):
        for journal in self:
            if journal.sync_with_exact_online and journal.sync_from_exact_online:
                raise UserError(_("You can only sync to Exact Online or sync from Exact Online, "
                                  "not both at the same time."))
            # if (journal.sync_with_exact_online or journal.sync_from_exact_online) and not journal.exact_online_code:
            #     raise UserError(_("If you want to sync this journal with Exact Online, "
            #                       "you need to enter the Exact Online code."))

    @api.model_create_multi
    def create(self, vals_list):
        journals = super(AccountJournal, self).create(vals_list)
        journals.exact_check_subscription_level()
        return journals

    def write(self, vals):
        res = super(AccountJournal, self).write(vals)
        if 'sync_with_exact_online' in vals or 'sync_from_exact_online' in vals or 'type' in vals:
            self.exact_check_subscription_level()
        return res

    @api.model
    def exact_get_subscription_level_domain(self, company):
        domain = [('company_id', '=', company.id)]
        if company.exact_online_subscription_level == 'standard':
            return domain + [('type', 'in', ['sale', 'purchase'])]
        return domain

    def exact_check_subscription_level(self, raise_exception=True):
        """
        Check journals to sync according to the Exact Online subscription level of the customer
        :param raise_exception: If True, raises an exception, if False, corrects the journal to not be synced if invalid
        :type raise_exception: bool
        """
        for journal in self:
            if not (journal.sync_with_exact_online_available or journal.sync_from_exact_online_available) \
                    and (journal.sync_with_exact_online or journal.exact_online_code):
                journal.write({
                    'sync_with_exact_online': False,
                    'exact_online_code': False,
                })
            else:
                if journal.sync_with_exact_online and journal.company_id.exact_online_active:
                    if journal.company_id.exact_online_subscription_level == 'standard' \
                            and journal.type not in ['sale', 'purchase']:
                        if raise_exception:
                            raise ValidationError(_("You can only sync sale and purchase journals with "
                                                    "a standard Exact Online subscription level"))
                        else:
                            journal.sync_with_exact_online = False
                if journal.sync_from_exact_online and journal.company_id.exact_online_active:
                    if journal.company_id.exact_online_subscription_level != 'advanced':
                        if raise_exception:
                            raise ValidationError(_("You can only get moves for journals from Exact Online "
                                                    "with an advanced Exact Online subscription level"))
                        else:
                            journal.sync_from_exact_online = False


class AccountPaymentTerm(models.Model):
    _name = 'account.payment.term'
    _inherit = ['account.payment.term', 'exact.data.mixin']


class AccountTax(models.Model):
    _name = 'account.tax'
    _inherit = ['account.tax', 'exact.data.mixin']
