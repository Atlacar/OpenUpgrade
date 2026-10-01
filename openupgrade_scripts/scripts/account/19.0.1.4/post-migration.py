# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from openupgradelib import openupgrade

from odoo.orm.commands import Command

_logger = logging.getLogger(__name__)


def account_reconcile_model(env):
    """
    Apply changes to account.reconcile.model
    """
    env.cr.execute(
        """
        UPDATE account_reconcile_model
        SET trigger='auto_reconcile'
        WHERE auto_reconcile
        """
    )


def account_reconcile_model_partner_mapping(env):
    """
    Model account.reconcile.model.partner.mapping is folded into
    account.reconcile.model.line, so create a new model per partner
    mapping, merge regexes from partner mapping and model if any
    """
    link_column = openupgrade.get_legacy_name("partner_mapping_id")
    env.cr.execute(
        "ALTER TABLE account_reconcile_model "
        f"ADD COLUMN IF NOT EXISTS {link_column} int "
    )
    env.cr.execute(
        """
        SELECT
        model_id,
        array_agg(id),
        array_agg(partner_id),
        array_agg(payment_ref_regex),
        array_agg(narration_regex)
        FROM account_reconcile_model_partner_mapping mapping
        GROUP BY model_id
        """
    )
    AccountReconcileModel = env["account.reconcile.model"]
    ResPartner = env["res.partner"]

    for (
        reconcile_model_id,
        mapping_ids,
        partner_ids,
        payment_ref_regexes,
        narration_regexes,
    ) in env.cr.fetchall():
        reconcile_model = AccountReconcileModel.browse(reconcile_model_id)
        match_regex_lookahead = ""
        if reconcile_model.match_label_param:
            if reconcile_model.match_label == "contains":
                match_regex_lookahead = (
                    f"(?=.*{re.escape(reconcile_model.match_label_param)}.*)"
                )
            elif reconcile_model.match_label == "not_contains":
                match_regex_lookahead = (
                    f"(?!{re.escape(reconcile_model.match_label_param)})"
                )
            elif reconcile_model.match_label == "match_regex":
                match_regex_lookahead = f"(?={reconcile_model.match_label_param})"

        for mapping_id, partner_id, payment_ref_regex, narration_regex in zip(
            mapping_ids,
            partner_ids,
            payment_ref_regexes,
            narration_regexes,
            strict=True,
        ):
            partner = ResPartner.browse(partner_id)
            match_regex = "|".join(
                map(
                    lambda x: f"({x})",
                    filter(None, [payment_ref_regex, narration_regex]),
                )
            )
            new_reconcile_model = reconcile_model.copy(
                {
                    "name": reconcile_model.name + f" ({partner.name})",
                    "match_label": "match_regex",
                    "match_label_param": match_regex_lookahead + match_regex,
                    "line_ids": [
                        Command.create(
                            {
                                "partner_id": partner_id,
                            }
                        ),
                    ],
                }
            )
            env.cr.execute(
                f"""
                UPDATE account_reconcile_model
                SET {link_column} = {mapping_id}
                WHERE id = {new_reconcile_model.id}
                """
            )


def account_account_active(env):
    """
    Set active flag from deprecated
    """
    env.cr.execute("UPDATE account_account SET active = FALSE where deprecated")


def fiscal_position_tax_ids(env):
    """
    Fill account.fiscal.position#tax_ids from previous account.fiscal.position.tax
    table
    """
    env.cr.execute(
        """
        INSERT INTO account_fiscal_position_account_tax_rel
        (account_fiscal_position_id, account_tax_id)
        SELECT DISTINCT position_id, tax_dest_id FROM account_fiscal_position_tax
        WHERE tax_dest_id IS NOT NULL
        """
    )


def account_tax_original_tax_ids(env):
    """
    Fill account.tax#original_tax_ids from previous account.fiscal.position.tax table
    """
    env.cr.execute(
        """
        INSERT INTO account_tax_alternatives
        (dest_tax_id, src_tax_id)
        SELECT DISTINCT tax_dest_id, tax_src_id FROM account_fiscal_position_tax
        WHERE tax_dest_id IS NOT NULL AND tax_src_id IS NOT NULL
        """
    )


def account_full_reconcile_exchange_move_id(env):
    """
    account.full.reconcile#exchange_move_id has been scrapped: the exchange move is
    linked to a partial reconciliation of the full reconcile instead, as v19 does in
    account.move.line#_create_reconciliation_partials (it sets exchange_move_id on an
    existing partial).

    The last partial of the full reconcile gets the exchange move when it has none.
    Otherwise a copy of it carrying the exchange move is created with zero amounts: a
    copy with the original amount would count the same match twice (residuals of
    both lines become -/+amount, invoices go back to partial, payments to in_process).
    """
    env.cr.execute(
        """
        SELECT afr.id, afr.exchange_move_id, last_partial.id,
            last_partial.exchange_move_id IS NOT NULL
        FROM account_full_reconcile afr
        JOIN LATERAL (
            SELECT apr.id, apr.exchange_move_id
            FROM account_partial_reconcile apr
            WHERE apr.full_reconcile_id = afr.id
            ORDER BY apr.id DESC
            LIMIT 1
        ) last_partial ON TRUE
        WHERE afr.exchange_move_id IS NOT NULL
        """
    )
    rows = env.cr.fetchall()
    free = [(move_id, partial_id) for _fr, move_id, partial_id, used in rows if not used]
    for exchange_move_id, partial_id in free:
        env.cr.execute(
            "UPDATE account_partial_reconcile SET exchange_move_id = %s WHERE id = %s",
            (exchange_move_id, partial_id),
        )
    copies = env["account.partial.reconcile"]
    for full_reconcile_id, exchange_move_id, partial_id, used in rows:
        if not used:
            continue
        copies |= (
            env["account.partial.reconcile"]
            .browse(partial_id)
            .copy(
                {
                    "exchange_move_id": exchange_move_id,
                    "full_reconcile_id": full_reconcile_id,
                    "amount": 0.0,
                    "debit_amount_currency": 0.0,
                    "credit_amount_currency": 0.0,
                }
            )
        )
    if copies:
        # the copies carry no amount, but make sure the residuals / payment states
        # of the reconciled items are (re)computed from the real partials
        lines = copies.debit_move_id | copies.credit_move_id
        aml_fields = env["account.move.line"]._fields
        for fname in ("amount_residual", "amount_residual_currency", "reconciled"):
            env.add_to_compute(aml_fields[fname], lines)
        move_fields = env["account.move"]._fields
        for fname in ("amount_residual", "amount_residual_signed", "payment_state"):
            env.add_to_compute(move_fields[fname], lines.move_id)
        env.flush_all()
    _logger.info(
        "account_full_reconcile_exchange_move_id: exchange move set on %s existing "
        "partial(s), %s zero-amount partial copy(ies)",
        len(free),
        len(copies),
    )


def account_move_line_no_followup(env):
    """
    Set no_followup = True on lines of journals of type 'general'
    """
    env.cr.execute(
        """
        UPDATE account_move_line
        SET no_followup=True
        FROM account_journal
        WHERE
        account_move_line.journal_id=account_journal.id AND
        account_journal.type = 'general'
        """
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "account", "19.0.1.4/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "account",
        [
            "email_template_edi_credit_note",
            "email_template_edi_invoice",
            "email_template_edi_self_billing_credit_note",
            "mail_template_data_payment_receipt",
        ],
        ["body_html"],
    )
    account_reconcile_model(env)
    account_reconcile_model_partner_mapping(env)
    account_account_active(env)
    fiscal_position_tax_ids(env)
    account_tax_original_tax_ids(env)
    account_full_reconcile_exchange_move_id(env)
    account_move_line_no_followup(env)
