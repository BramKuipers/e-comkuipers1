# -*- coding: utf-8 -*-
import base64
import logging

from datetime import time

from odoo import fields, models, api, _
from odoo.exceptions import UserError, AccessError
from odoo.tools.safe_eval import safe_eval


_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'exact.sync.mixin']

    exact_online_journal_synced = fields.Boolean(related='journal_id.sync_with_exact_online', readonly=True)

    def exact_handle_create(self):
        pass

    def exact_handle_write(self, vals):
        pass

    # Moves should only be synced when they are posted, from that moment on they are relevant to Exact.
    def _post(self, soft=True):
        posted = super(AccountMove, self)._post(soft)
        posted.create_print_attachment()
        posted.exact_create_transaction()
        return posted

    def exact_create_transaction(self, companies=None, initial=False):
        """ Overwrite default behaviour since a move can only be synced for it's own company and if it is in range """
        for record in self:
            company = record.company_id
            if company.exact_online_active or initial:
                if record.journal_id.sync_with_exact_online and (not company.exact_online_sync_from or company.exact_online_sync_from <= record.date):
                    record.exact_check_required_fields(initial)
                    super(AccountMove, record).exact_create_transaction(company, initial)

    def exact_check_required_fields(self, initial=False):
        for move in self:
            if not move.partner_id.exact_online_code:
                if not move.partner_id.exact_online_state not in ['queued', 'syncing'] and not initial:
                    raise UserError(_("Relation {} is not synced with Exact Online. "
                                      "Please make sure it is synced before posting this move."
                                      ).format(move.partner_id.display_name))
            if move.invoice_payment_term_id:
                if not move.invoice_payment_term_id.exact_online_code:
                    raise UserError(_("Payment term {} does not have an Exact Online code. "
                                      "Please make sure it is has one before posting this move."
                                      ).format(move.invoice_payment_term_id.display_name))
            for line in move.line_ids.filtered(lambda l: not l.display_type):
                if not line.account_id.exact_online_code:  # TODO: Actually check with Exact Online
                    raise UserError(_("Account {} does not have an Exact Online code. "
                                      "Please make sure it has one before posting this move."
                                      ).format(line.account_id.display_name))
                for tax in line.tax_ids:
                    if not tax.exact_online_code:
                        raise UserError(_("Tax {} does not have an Exact Online code. "
                                          "Please make sure it is has one before posting this move."
                                          ).format(tax.display_name))

    def create_print_attachment(self):
        if self.user_has_groups('account.group_account_invoice'):
            report = self.env.ref('account.account_invoices')
        else:
            report = self.env.ref('account.account_invoices_without_payment')
        # Set the default_type to binary since we could have a different default type via the moves.
        report = report.with_context(default_type='binary')
        IRAttachment = self.env['ir.attachment'].sudo().with_context(default_type='binary')
        for move in self:
            # Only automatically create pdf's for sales moves if the invoice doesn't have a .pdf attachment
            # already, this should ensure an attachment exists the moment the invoice is sent to Exact Online
            if move.move_type in ['out_invoice', 'out_refund']:
                domain = [('res_model', '=', self._name), ('res_id', '=', move.id), ('name', '=ilike', '%.pdf')]
                if not IRAttachment.search_count(domain):
                    pdf = report._render_qweb_pdf([move.id])
                    # Check again, report might have been saved in the attachment during the generation of the pdf
                    # and we don't want double attachments automatically
                    if not IRAttachment.search_count(domain):
                        attachment_name = safe_eval(report.attachment, {'object': move, 'time': time}) if report.attachment else ''
                        if not attachment_name:
                            continue
                        attachment_vals = {
                            'name': attachment_name,
                            'datas': base64.encodestring(pdf[0]),
                            'datas_fname': attachment_name,
                            'res_model': self._name,
                            'res_id': move.id,
                            'type': 'binary',
                        }
                        try:
                            self.env['ir.attachment'].create(attachment_vals)
                        except AccessError:
                            _logger.info("Cannot save PDF report %r as attachment", attachment_vals['name'])
                        else:
                            _logger.info('The PDF document %s is now saved in the database', attachment_vals['name'])
