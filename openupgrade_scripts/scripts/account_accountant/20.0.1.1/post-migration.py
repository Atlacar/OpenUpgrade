# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def account_account_is_deferred(env):
    """account.account#is_deferred is new: deferred dates are only shown/required
    on the lines of accounts flagged as deferred. Flag the accounts that already
    have journal items with a deferral period, so that existing deferred data stays
    visible (prod: 0 such lines)."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_account
        SET is_deferred = TRUE
        WHERE id IN (
            SELECT DISTINCT account_id
            FROM account_move_line
            WHERE deferred_start_date IS NOT NULL
        )
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    account_account_is_deferred(env)
