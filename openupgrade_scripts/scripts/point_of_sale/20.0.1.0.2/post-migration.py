# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

from odoo import Command

_logger = logging.getLogger(__name__)


def pos_config_closing_journal(env):
    """
    The pre script pre-filled the new required pos.config#closing_journal_id with the
    invoice journal. v20 uses a dedicated sale journal ("Point of Sale Closing", code
    POSC) for the session closing entries: create it per company like the
    field's compute does and use it.
    """
    cr = env.cr
    cr.execute("SELECT DISTINCT company_id FROM pos_config")
    for (company_id,) in cr.fetchall():
        company = env["res.company"].browse(company_id)
        journal = (
            env["account.journal"]
            .with_company(company)
            ._ensure_company_closing_journal()
        )
        openupgrade.logged_query(
            cr,
            "UPDATE pos_config SET closing_journal_id = %s WHERE company_id = %s",
            (journal.id, company.id),
        )


def pos_config_default_partner(env):
    """
    pos.config#default_partner_id is new, required and defaults to a partner created
    on the fly when the column is initialized, i.e. before the data file creates
    point_of_sale.default_session_closing_partner. Make the configs use the xmlid
    partner and drop the duplicates.
    """
    cr = env.cr
    partner = env.ref("point_of_sale.default_session_closing_partner")
    cr.execute(
        "SELECT DISTINCT default_partner_id FROM pos_config "
        "WHERE default_partner_id IS NOT NULL AND default_partner_id != %s",
        (partner.id,),
    )
    duplicates = [row[0] for row in cr.fetchall()]
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_config SET default_partner_id = %s
        WHERE default_partner_id IS NULL OR default_partner_id != %s
        """,
        (partner.id, partner.id),
    )
    configs = env["pos.config"].with_context(active_test=False).search([])
    for company in configs.company_id:
        receivable = company.account_default_pos_receivable_account_id
        if receivable:
            partner.with_company(company).property_account_receivable_id = receivable
    for duplicate in env["res.partner"].with_context(active_test=False).browse(
        duplicates
    ):
        if duplicate.name != partner.name or duplicate.active:
            continue
        try:
            with env.cr.savepoint():
                duplicate.unlink()
        except Exception as e:  # noqa: BLE001
            _logger.warning(
                "Could not delete duplicate default partner %s: %s", duplicate.id, e
            )


def pos_session_bank_statements(env):
    """
    v19 booked the cash of a session as account.bank.statement.line records
    (pos.session#statement_line_ids, no statement) with the opening/closing counts in
    pos.session#cash_register_balance_start / _end_real. v20 gives every session with
    a cash payment method one account.bank.statement (pos.session#bank_statement_id)
    whose balance_start / balance_end_real are the opening / closing balances shown on
    the session. Create it for the existing sessions.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "pos_session", "cash_journal_id"):
        return
    cr.execute(
        """
        SELECT id, name, state, cash_journal_id,
               cash_register_balance_start, cash_register_balance_end_real
        FROM pos_session
        WHERE bank_statement_id IS NULL AND cash_journal_id IS NOT NULL
        ORDER BY id
        """
    )
    sessions = cr.fetchall()
    created = failed = 0
    for session in sessions:
        session_id, name, state, journal_id, balance_start, balance_end_real = session
        cr.execute(
            """
            SELECT id FROM account_bank_statement_line
            WHERE pos_session_id = %s AND statement_id IS NULL
            """,
            (session_id,),
        )
        line_ids = [row[0] for row in cr.fetchall()]
        method = env["pos.payment.method"].search(
            [("journal_id", "=", journal_id)], limit=1
        )
        vals = {
            "name": "Cash Statement for %s in %s"
            % (method.name or env["account.journal"].browse(journal_id).name, name),
            "journal_id": journal_id,
            "balance_start": balance_start or 0.0,
            "line_ids": [Command.set(line_ids)],
        }
        if state == "closed":
            vals["balance_end_real"] = balance_end_real or 0.0
        try:
            with cr.savepoint():
                statement = env["account.bank.statement"].create(vals)
                cr.execute(
                    "UPDATE pos_session SET bank_statement_id = %s WHERE id = %s",
                    (statement.id, session_id),
                )
            created += 1
        except Exception:
            _logger.exception(
                "Could not create the cash statement of pos.session %s", session_id
            )
            failed += 1
    _logger.info(
        "Created %s cash statements for %s sessions (%s failed)",
        created,
        len(sessions),
        failed,
    )
    # The cash payment method points to the latest statement of its journal
    # (point of sale > cash control button)
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE pos_payment_method pm
        SET account_bank_statement_id = last.bank_statement_id
        FROM (
            SELECT DISTINCT ON (cash_journal_id) cash_journal_id, bank_statement_id
            FROM pos_session
            WHERE bank_statement_id IS NOT NULL
            ORDER BY cash_journal_id, id DESC
        ) last
        WHERE pm.journal_id = last.cash_journal_id
        AND pm.type = 'cash'
        AND pm.account_bank_statement_id IS NULL
        """,
    )


def pos_session_move(env):
    """
    pos.session#move_id (the one closing journal entry) is now split in
    sale_move_ids / refund_move_ids (account.move#pos_session_sales_id / _refunds_id).
    The v19 entry mixed both: link it as the sales entry of the session.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "pos_session", "move_id"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_move am
        SET pos_session_sales_id = ps.id
        FROM pos_session ps
        WHERE ps.move_id = am.id AND am.pos_session_sales_id IS NULL
        """,
    )


def pos_config_preparation_devices(env):
    """
    New pos.config#preparation_devices switches the preparation printers feature
    on, v19 had no switch (is_order_printer, now use_order_printer, did it).
    """
    cr = env.cr
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_config pc
        SET preparation_devices = TRUE
        WHERE use_order_printer
        OR EXISTS (SELECT 1 FROM pos_config_printer_rel r WHERE r.config_id = pc.id)
        """,
    )


def pos_printer_fields(env):
    """
    pos.printer: the printer address is a single field (printer_ip), the 'iot' printer
    type is gone
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "pos_printer", "epson_printer_ip"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_printer
        SET printer_ip = COALESCE(epson_printer_ip, proxy_ip)
        WHERE printer_ip IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        "UPDATE pos_printer SET printer_type = 'epson_epos' "
        "WHERE printer_type = 'iot'",
    )


def pos_config_sequences(env):
    """
    pos.config#order_seq_id, order_backend_seq_id, order_line_seq_id and device_seq_id
    are unchanged since v19 (19.0 migration created them, v20 reads the placeholders
    of the prefix/suffix with ir.sequence#_get_prefix_suffix, so the v18 placeholder
    sequences no longer break the order numbering). Only make sure that every
    config has them.
    """
    sequence_fields = (
        ("order_seq_id", "POS order from config #%s", 6),
        ("order_backend_seq_id", "POS order backend from config #%s", 6),
        ("order_line_seq_id", "POS order line from config #%s", 6),
        ("device_seq_id", "POS device from config #%s", 0),
    )
    for config in env["pos.config"].with_context(active_test=False).search([]):
        for fname, name, padding in sequence_fields:
            if config[fname]:
                continue
            _logger.warning("pos.config %s has no %s, creating it", config.id, fname)
            config[fname] = (
                env["ir.sequence"]
                .sudo()
                .create(
                    {
                        "name": name % config.id,
                        "padding": padding,
                        "code": "pos.order",
                        "company_id": config.company_id.id,
                        "implementation": "no_gap",
                    }
                )
            )


def set_not_null(env):
    """
    Required fields filled by the steps above: the ORM could not set the NOT NULL
    constraint when it initialized the columns.
    """
    cr = env.cr
    for table, column in (
        ("pos_config", "closing_journal_id"),
        ("pos_config", "default_partner_id"),
    ):
        cr.execute(f"SELECT 1 FROM {table} WHERE {column} IS NULL LIMIT 1")
        if cr.rowcount:
            _logger.warning("%s.%s still has NULL values", table, column)
            continue
        openupgrade.logged_query(
            cr, f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"
        )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "point_of_sale", "20.0.1.0.2/noupdate_changes.xml")
    pos_config_closing_journal(env)
    pos_config_default_partner(env)
    pos_session_bank_statements(env)
    pos_session_move(env)
    pos_config_preparation_devices(env)
    pos_printer_fields(env)
    pos_config_sequences(env)
    set_not_null(env)
