# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def account_return_check_template_cycle(env):
    """account.return.check.template#cycle (selection, required) is replaced by
    cycle_id (m2o to the new account.return.audit.cycle). The codes of the cycles
    created by the 20.0 data are the old selection keys. Shipped templates are
    reloaded from data with their cycle; this covers custom templates and the
    rows for which the data does not set a cycle (prod: 49 shipped templates)."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "account_return_check_template", "cycle"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_return_check_template t
        SET cycle_id = c.id
        FROM account_return_audit_cycle c
        WHERE c.code = t.cycle AND t.cycle_id IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_return_check_template t
        SET cycle_id = c.id
        FROM account_return_audit_cycle c
        WHERE c.code = 'other' AND t.cycle_id IS NULL
        """,
    )


def account_return_type_payment_partner(env):
    """payment_partner_id was related to the partner of payment_partner_bank_id,
    it is now a stored field (the bank is computed from it)."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_return_type t
        SET payment_partner_id = b.partner_id
        FROM res_partner_bank b
        WHERE b.id = t.payment_partner_bank_id AND t.payment_partner_id IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    account_return_check_template_cycle(env)
    account_return_type_payment_partner(env)
