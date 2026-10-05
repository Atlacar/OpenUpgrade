# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def res_partner_bank_clabe(env):
    """res.partner.bank#l10n_mx_edi_clabe and res.bank#l10n_mx_edi_code are removed.

    Structure in 20.0 (base res_partner_bank, account res_partner_bank,
    odoo/tools/bank_account_number.py):
    - the CLABE is the account number itself: ``account_type`` 'clabe' is inferred
      from an 18 digit account number with a valid checksum (not stored);
    - the clearing label of Mexico is "ABM Code" (base.clearing_label_mx), i.e.
      the 3 digit bank code that was ``res.bank.l10n_mx_edi_code`` in 19.0 (and
      is the first 3 digits of a CLABE).
    So the ABM code goes to ``clearing_number`` (with the Mexican label), the
    CLABE stays where it is when it equals the account number (prod: 8 of 9
    accounts). The CLABE cannot be stored structurally when it differs from the
    account number (prod: "0123969479-Overland", CLABE 012210001239694792, partner 31): the account number is kept as is (it identifies
    the account in the 2 outbound customer payments and the credit note that use it), and the CLABE
    is kept in the notes and in the legacy column openupgrade_legacy_20_0_l10n_mx_edi_clabe.
    Owner decision 2026-10-04: keep as is, do not restructure, add or delete."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "res_partner_bank", "l10n_mx_edi_clabe"):
        return
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = 'base' AND name = 'clearing_label_mx'
            AND model = 'clearing.label'
        """
    )
    row = cr.fetchone()
    if not row:
        _logger.warning("clearing.label base.clearing_label_mx not found")
        return
    label_id = row[0]
    has_bank_code = openupgrade.table_exists(cr, "res_bank") and (
        openupgrade.column_exists(cr, "res_bank", "l10n_mx_edi_code")
        and openupgrade.column_exists(cr, "res_partner_bank", "bank_id")
    )
    bank_code = (
        "(SELECT NULLIF(rb.l10n_mx_edi_code, '') FROM res_bank rb "
        "WHERE rb.id = rpb.bank_id)"
        if has_bank_code
        else "NULL"
    )
    # ABM code -> clearing number of the Mexican bank accounts (label ABM Code);
    # without a bank, the first 3 digits of a valid-looking 18 digits CLABE
    openupgrade.logged_query(
        cr,
        f"""
        UPDATE res_partner_bank rpb
        SET clearing_label_id = %(label)s,
            clearing_number = COALESCE(
                {bank_code},
                CASE WHEN rpb.l10n_mx_edi_clabe ~ '^[0-9]{{18}}$'
                    THEN left(rpb.l10n_mx_edi_clabe, 3) END
            )
        FROM res_country c
        WHERE c.id = rpb.country_id AND c.code = 'MX'
            AND COALESCE(rpb.clearing_number, '') = ''
            AND COALESCE(
                {bank_code},
                CASE WHEN rpb.l10n_mx_edi_clabe ~ '^[0-9]{{18}}$'
                    THEN left(rpb.l10n_mx_edi_clabe, 3) END
            ) IS NOT NULL
        """,
        {"label": label_id},
    )
    # legacy copy of every CLABE (the original column is never dropped by the
    # framework, but the copy is the documented place of the value)
    openupgrade.copy_columns(
        cr, {"res_partner_bank": [("l10n_mx_edi_clabe", None, None)]}
    )
    # CLABE different from the account number: cannot be stored structurally
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_partner_bank
        SET note = concat_ws(E'\n', note, 'CLABE: ' || l10n_mx_edi_clabe)
        WHERE COALESCE(l10n_mx_edi_clabe, '') != ''
            AND account_number IS DISTINCT FROM l10n_mx_edi_clabe
            AND COALESCE(note, '') NOT LIKE '%%' || l10n_mx_edi_clabe || '%%'
        """,
    )
    cr.execute(
        """
        SELECT id, account_number, l10n_mx_edi_clabe FROM res_partner_bank
        WHERE COALESCE(l10n_mx_edi_clabe, '') != ''
            AND account_number IS DISTINCT FROM l10n_mx_edi_clabe
        """
    )
    for bank_id, number, clabe in cr.fetchall():
        _logger.warning(
            "res.partner.bank %s: account number %r differs from its CLABE %s; the "
            "CLABE is kept in the notes (20.0 stores the CLABE as account number).",
            bank_id,
            number,
            clabe,
        )


@openupgrade.migrate()
def migrate(env, version):
    res_partner_bank_clabe(env)
