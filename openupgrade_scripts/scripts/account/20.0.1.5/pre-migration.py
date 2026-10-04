# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade

from odoo.exceptions import UserError

_renamed_xmlids = [
    # stock valuation closing moved from stock_account to account
    (
        "stock_account.ir_cron_post_stock_valuation",
        "account.ir_cron_post_stock_valuation",
    ),
    (
        "stock_account.action_report_stock_valuation",
        "account.action_report_stock_valuation",
    ),
]


def account_move_review_state(env):
    """account.move#checked (boolean) is replaced by account.move#review_state
    (required selection, default 'no_review').

    - checked            -> reviewed
    - posted, not checked -> todo (it was shown in the "To Review" list)
    - otherwise          -> no_review
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "account_move", "review_state"):
        cr.execute("ALTER TABLE account_move ADD COLUMN review_state varchar")
    cr.execute(
        """
        UPDATE account_move
        SET review_state = CASE
            WHEN checked IS TRUE THEN 'reviewed'
            WHEN state = 'posted' THEN 'todo'
            ELSE 'no_review'
        END
        WHERE review_state IS NULL
        """
    )


def account_move_document_tax_mode(env):
    """account.move#document_tax_mode is new (stored, NULL for non invoices). The
    19.0 tax price_include was derived from the company default, so use the same
    default as the 20.0 compute method (company.account_price_include) for every
    invoice-like move. Pre-filled here because the new constraint
    check_document_tax_mode_set requires it on invoices.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "account_move", "document_tax_mode"):
        cr.execute("ALTER TABLE account_move ADD COLUMN document_tax_mode varchar")
    cr.execute(
        """
        UPDATE account_move am
        SET document_tax_mode = COALESCE(
            NULLIF(rc.account_price_include, ''), 'tax_excluded')
        FROM res_company rc
        WHERE rc.id = am.company_id
            AND am.document_tax_mode IS NULL
            AND am.move_type IN (
                'out_invoice', 'out_refund', 'in_invoice', 'in_refund',
                'out_receipt', 'in_receipt')
        """
    )


def account_move_line_deductible_percentage(env):
    """deductible_amount (percentage, 0-100, default 100) becomes
    deductible_percentage (ratio 0-1, default 1)."""
    cr = env.cr
    if openupgrade.column_exists(cr, "account_move_line", "deductible_amount"):
        # sanity check: the percentage must be within 0..100, otherwise the
        # ratio would be wrong silently (prod: 55758 rows, all 100)
        cr.execute(
            """
            SELECT count(*), min(deductible_amount), max(deductible_amount)
            FROM account_move_line
            WHERE deductible_amount < 0 OR deductible_amount > 100
            """
        )
        count, minimum, maximum = cr.fetchone()
        if count:
            raise UserError(
                f"Migration aborted: {count} account.move.line row(s) have a "
                f"deductible_amount outside 0..100 (min {minimum}, max {maximum}). "
                "Correct them in Odoo 19 (e.g. SELECT id, deductible_amount FROM "
                "account_move_line WHERE deductible_amount < 0 OR "
                "deductible_amount > 100) before migrating."
            )
    if not openupgrade.column_exists(cr, "account_move_line", "deductible_percentage"):
        cr.execute(
            "ALTER TABLE account_move_line "
            "ADD COLUMN deductible_percentage double precision"
        )
    cr.execute(
        """
        UPDATE account_move_line
        SET deductible_percentage = COALESCE(deductible_amount, 100.0) / 100.0
        WHERE deductible_percentage IS NULL
        """
    )


def account_payment_state(env):
    """account.payment#state: 'in_process' is removed and the meaning of 'paid'
    changed.

    19.0: in_process = posted, liquidity not yet matched with a bank statement;
          paid = liquidity matched (or no reconcilable outstanding account).
    20.0: paid = posted; reconciled = liquidity matched / zero residual (this is
          what the 20.0 _compute_state gives).
    So: paid -> reconciled, in_process -> paid.
    """
    env.cr.execute(
        """
        UPDATE account_payment
        SET state = CASE state
            WHEN 'paid' THEN 'reconciled'
            WHEN 'in_process' THEN 'paid'
            ELSE state
        END
        WHERE state IN ('paid', 'in_process')
        """
    )


def account_reconcile_model(env):
    """The columns rule_type, matching_order, payment_tolerance_type,
    allow_payment_tolerance and payment_tolerance_param are orphans of the 18.0
    enterprise module that survived in the 19.0 database (no ir.model.fields
    row). 20.0 defines rule_type / matching_order / payment_tolerance(_type) on
    account in CE with other semantics:

    - rule_type: writeoff_button / invoice_matching -> reco_model / matching_rule
      (matching_rule goes with trigger = auto_reconcile, see _compute_trigger)
    - payment_tolerance_param (if allowed) -> payment_tolerance
    """
    cr = env.cr
    if openupgrade.column_exists(cr, "account_reconcile_model", "rule_type"):
        cr.execute(
            """
            UPDATE account_reconcile_model
            SET rule_type = CASE
                WHEN trigger = 'auto_reconcile' THEN 'matching_rule'
                ELSE 'reco_model'
            END
            WHERE rule_type IS NULL
                OR rule_type NOT IN ('matching_rule', 'reco_model')
            """
        )
    if openupgrade.column_exists(cr, "account_reconcile_model", "matching_order"):
        cr.execute(
            """
            UPDATE account_reconcile_model
            SET matching_order = 'old_first'
            WHERE matching_order IS NULL
                OR matching_order NOT IN ('new_first', 'old_first')
            """
        )
    if openupgrade.column_exists(
        cr, "account_reconcile_model", "payment_tolerance_type"
    ):
        cr.execute(
            """
            UPDATE account_reconcile_model
            SET payment_tolerance_type = 'percentage'
            WHERE payment_tolerance_type IS NULL
                OR payment_tolerance_type NOT IN ('amount', 'percentage')
            """
        )
    if not openupgrade.column_exists(
        cr, "account_reconcile_model", "payment_tolerance"
    ):
        cr.execute(
            "ALTER TABLE account_reconcile_model "
            "ADD COLUMN payment_tolerance double precision"
        )
        if openupgrade.column_exists(
            cr, "account_reconcile_model", "payment_tolerance_param"
        ):
            cr.execute(
                """
                UPDATE account_reconcile_model
                SET payment_tolerance = CASE
                    WHEN allow_payment_tolerance IS TRUE
                    THEN COALESCE(payment_tolerance_param, 0.0)
                    ELSE 0.0
                END
                """
            )
        else:
            cr.execute("UPDATE account_reconcile_model SET payment_tolerance = 0.0")


def account_report(env):
    """account.report#active is not stored anymore: it is computed from
    active_selection (company dependent) and active_fallback. Keep the
    archived state in active_fallback.
    account.report.line#foldable is replaced by foldability: keep the legacy
    column to set foldability = 'foldable' in post-migration.
    account.report.column#report_id is now required: remove orphans.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "account_report", "active_fallback"):
        cr.execute("ALTER TABLE account_report ADD COLUMN active_fallback boolean")
    cr.execute(
        """
        UPDATE account_report
        SET active_fallback = COALESCE(active, TRUE)
        WHERE active_fallback IS NULL
        """
    )
    openupgrade.copy_columns(cr, {"account_report_line": [("foldable", None, None)]})
    cr.execute("DELETE FROM account_report_column WHERE report_id IS NULL")


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
    account_move_review_state(env)
    account_move_document_tax_mode(env)
    account_move_line_deductible_percentage(env)
    account_payment_state(env)
    account_reconcile_model(env)
    account_report(env)
