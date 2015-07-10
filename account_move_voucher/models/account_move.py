# -*- coding: utf-8 -*-
from openerp import fields, models, api, _
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)


class account_move(models.Model):
    _inherit = 'account.move'

    # residual_type = fields.Selection([
    #     ('receivable', 'Receivable'),
    #     ('payable', 'Payable'),
    #     ],
    #     string='Residual Type')
    receivable_residual = fields.Float(
        string='Receivable Balance',
        digits=dp.get_precision('Account'),
        compute='_compute_residual',
        # store=True,
        help="Remaining receivable amount due."
        )
    payable_residual = fields.Float(
        string='Payable Balance',
        digits=dp.get_precision('Account'),
        compute='_compute_residual',
        # store=True,
        help="Remaining payable amount due."
        )

    @api.one
    @api.depends(
        'state',
        'line_id.account_id.type',
        'line_id.amount_residual',
        # Fixes the fact that move_id.line_id.amount_residual, being not stored and old API, doesn't trigger recomputation
        'line_id.reconcile_id',
        # 'line_id.amount_residual_currency',
        # 'line_id.currency_id',
        'line_id.reconcile_partial_id.line_partial_ids',
        # 'line_id.reconcile_partial_id.line_partial_ids.invoice.type',
    )
    def _compute_residual(self):
        # TODO tal vez falta agregar lo de multi currency de donde lo sacamos
        # de invoice
        payable_residual = 0.0
        receivable_residual = 0.0
        # Each partial reconciliation is considered only once for each invoice
        # it appears into,
        # and its residual amount is divided by this number of invoices
        partial_reconciliations_done = []
        for line in self.sudo().line_id:
            if line.account_id.type not in ('receivable', 'payable'):
                continue
            if line.reconcile_partial_id and line.reconcile_partial_id.id in partial_reconciliations_done:
                continue
            # Get the correct line residual amount
            line_amount = line.amount_residual_currency if line.currency_id else line.amount_residual
            # For partially reconciled lines, split the residual amount
            if line.reconcile_partial_id:
                raise Warning(_('Partial reconciliation not implemented yet'))
                partial_reconciliation_lines = line.mapped(
                    'reconcile_partial_id.line_partial_ids')
                line_amount = self.company_id.currency_id.round(
                    line_amount / len(partial_reconciliation_lines))
                partial_reconciliations_done.append(
                    line.reconcile_partial_id.id)
            if line.account_id.type == 'receivable':
                payable_residual += line_amount
            else:
                receivable_residual += line_amount
        self.payable_residual = max(payable_residual, 0.0)
        self.receivable_residual = max(receivable_residual, 0.0)

    @api.multi
    def action_create_receipt_voucher(self):
        return self.create_voucher('receipt')

    @api.multi
    def action_create_payment_voucher(self):
        return self.create_voucher('payment')

    @api.multi
    def create_voucher(self, voucher_type):
        # todo ver como podemos incorporar cobros, si es que tiene sentido
        self.ensure_one()
        view_id = self.env['ir.model.data'].xmlid_to_res_id(
            'account_voucher.view_vendor_receipt_dialog_form')
        return {
            'name': _("Pay Settlement"),
            'view_mode': 'form',
            'view_id': view_id,
            'view_type': 'form',
            'res_model': 'account.voucher',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'new',
            'domain': '[]',
            'context': {
                'payment_expected_currency': self.company_id.currency_id.id,
                'default_partner_id': self.partner_id.id,
                'default_amount': self.residual_amount,
                'default_reference': self.name,
                'close_after_process': True,
                # 'invoice_type': self.type,
                # 'invoice_id': self.id,
                'default_type': voucher_type,
                'type': 'voucher_type'
            }
        }
