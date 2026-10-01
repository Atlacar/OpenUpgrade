# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade

_renamed_xmlids = [
    # the stock valuation menu moved from stock_accountant to account_reports
    (
        "stock_accountant.menu_action_stock_account_report_stock_valuation",
        "account_reports.menu_action_stock_account_report_stock_valuation",
    ),
]

_GENERIC_STATE_COLUMNS = [
    "generic_state_review",
    "generic_state_review_submit",
    "generic_state_tax_report",
    "generic_state_only_pay",
]


def account_return_generic_state(env):
    """The 'new' key of the generic_state_* selections is removed (default 'new'
    in 19.0): a return without state value is a new return in 20.0."""
    for column in _GENERIC_STATE_COLUMNS:
        if openupgrade.column_exists(env.cr, "account_return", column):
            openupgrade.logged_query(
                env.cr,
                f"UPDATE account_return SET {column} = NULL WHERE {column} = 'new'",
            )


_OBSOLETE_BANK_REC_LINES = [
    # deleted lines of the bank reconciliation report, listed leaves first
    "unreconciled_last_statement_receipts",
    "unreconciled_last_statement_payments",
    "last_statement_balance",
    "no_statement_unreconciled_receipt",
    "no_statement_unreconciled_payments",
    "transaction_without_statement",
    "balance_bank",
]


_OBSOLETE_BANK_REC_EXPRESSIONS = [
    "account_financial_report_net_profit_after_allocations0_balance",
    "balance_bank_expr",
    "balance_bank_expr_forced_currency_amount",
    "last_statement_balance_amount",
    "last_statement_balance_forced_currency_amount",
    "misc_operations_amount_forced_currency_amount",
    "no_statement_unreconciled_payments_amount",
    "no_statement_unreconciled_payments_amount_currency",
    "no_statement_unreconciled_payments_currency",
    "no_statement_unreconciled_payments_date",
    "no_statement_unreconciled_payments_forced_currency_amount",
    "no_statement_unreconciled_payments_forced_currency_amount_currency",
    "no_statement_unreconciled_payments_label",
    "no_statement_unreconciled_receipt_amount",
    "no_statement_unreconciled_receipt_amount_currency",
    "no_statement_unreconciled_receipt_currency",
    "no_statement_unreconciled_receipt_date",
    "no_statement_unreconciled_receipt_forced_currency_amount",
    "no_statement_unreconciled_receipt_forced_currency_amount_currency",
    "no_statement_unreconciled_receipt_label",
    "outstanding_payments_currency",
    "outstanding_receipts_currency",
    "transaction_without_statement_expr",
    "transaction_without_statement_expr_forced_currency_amount",
    "unreconciled_last_statement_payments_amount",
    "unreconciled_last_statement_payments_amount_currency",
    "unreconciled_last_statement_payments_currency",
    "unreconciled_last_statement_payments_date",
    "unreconciled_last_statement_payments_forced_currency_amount",
    "unreconciled_last_statement_payments_forced_currency_amount_currency",
    "unreconciled_last_statement_payments_label",
    "unreconciled_last_statement_receipts_amount",
    "unreconciled_last_statement_receipts_amount_currency",
    "unreconciled_last_statement_receipts_currency",
    "unreconciled_last_statement_receipts_date",
    "unreconciled_last_statement_receipts_forced_currency_amount",
    "unreconciled_last_statement_receipts_forced_currency_amount_currency",
    "unreconciled_last_statement_receipts_label",
]


def bank_reconciliation_report_lines(env):
    """The bank reconciliation report was restructured: the 19 lines
    no_statement_unreconciled_payments (code unreconciled_payments) etc. are
    deleted, and the new line with the same code (unreconciled_payments) would
    hit the unique (report_id, code) constraint while loading the data."""
    # keep the lines that still exist in 20 (misc_operations) alive: the old
    # parent is deleted, so detach them first (parent_id cascades on delete)
    env.cr.execute(
        """
        UPDATE account_report_line l SET parent_id = NULL
        FROM ir_model_data imd
        WHERE imd.model = 'account.report.line' AND imd.res_id = l.id
            AND imd.module = 'account_reports'
            AND imd.name IN ('misc_operations', 'outstanding')
        """
    )
    # expressions first: a renamed expression with the same (line, label) as a
    # new one would hit account_report_expression_line_label_uniq at data load
    openupgrade.delete_records_safely_by_xml_id(
        env, ["account_reports." + name for name in _OBSOLETE_BANK_REC_EXPRESSIONS]
    )
    for name in _OBSOLETE_BANK_REC_LINES:
        openupgrade.delete_records_safely_by_xml_id(
            env, ["account_reports." + name]
        )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
    account_return_generic_state(env)
    bank_reconciliation_report_lines(env)
