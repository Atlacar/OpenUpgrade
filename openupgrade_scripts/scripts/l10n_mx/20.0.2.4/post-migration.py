# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def res_partner_bank_clabe(env):
    """res.partner.bank#l10n_mx_edi_clabe is removed: in 20.0 the CLABE is the
    account number itself (account_type 'clabe' is inferred from it, see
    base/account res_partner_bank). When the stored CLABE is the account number
    (prod: 8 of 9 accounts) nothing is needed. When it differs (prod: 1 account,
    "0123969479-Overland" with CLABE 012210001239694792) the account number is left
    untouched (it identifies the bank account in statement imports and journals)
    and the CLABE is kept in the notes of the bank account."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "res_partner_bank", "l10n_mx_edi_clabe"):
        return
    number_column = (
        "account_number"
        if openupgrade.column_exists(cr, "res_partner_bank", "account_number")
        else "acc_number"
    )
    openupgrade.logged_query(
        cr,
        f"""
        UPDATE res_partner_bank
        SET note = concat_ws(E'\n', note, 'CLABE: ' || l10n_mx_edi_clabe)
        WHERE COALESCE(l10n_mx_edi_clabe, '') != ''
            AND {number_column} IS DISTINCT FROM l10n_mx_edi_clabe
            AND COALESCE(note, '') NOT LIKE '%%' || l10n_mx_edi_clabe || '%%'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    res_partner_bank_clabe(env)
