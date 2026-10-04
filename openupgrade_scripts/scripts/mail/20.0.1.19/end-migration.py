# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

LEGACY_TRACKING_TABLE = "openupgrade_legacy_20_0_mail_tracking_value"


def _check_tracking_rows(env):
    """Hard gate "0 unexplained tracking rows lost": compare the rows copied in
    pre-migration (``LEGACY_TRACKING_TABLE``) with mail_tracking_value once all
    modules are loaded. A row may only disappear when its message was deleted
    because the model of the record no longer exists in 20 (stock.scrap: see
    post-migration ``_keep_scrap_messages``). Everything else is logged as ERROR.
    Rows created during the run (id not in the legacy copy) are only counted.
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, LEGACY_TRACKING_TABLE):
        return
    if not openupgrade.table_exists(cr, "mail_tracking_value"):
        _logger.error(
            "mail_tracking_value does not exist after the migration "
            "(mail_tracking not installed?), the raw rows are in %s",
            LEGACY_TRACKING_TABLE,
        )
        return
    cr.execute(f"SELECT COUNT(*) FROM {LEGACY_TRACKING_TABLE}")  # noqa: E8103
    before = cr.fetchone()[0]
    # The obsolete ir.model records (and with them, through
    # mail.ir_model._unlink_related_mail_data, the messages and their tracking rows)
    # are only deleted at the very end of the registry load, i.e. AFTER this script.
    # So "explained" = the message model is not in the registry any more: the row is
    # either already gone or still there but will go with its message.
    cr.execute(
        f"""
        SELECT l.id, l.legacy_message_model,
            EXISTS (SELECT 1 FROM mail_tracking_value t WHERE t.id = l.id)
        FROM {LEGACY_TRACKING_TABLE} l
        ORDER BY l.id
        """  # noqa: E8103
    )
    rows = cr.fetchall()
    explained = [row for row in rows if row[1] and row[1] not in env.registry]
    explained_ids = {row[0] for row in explained}
    unexplained = [row for row in rows if not row[2] and row[0] not in explained_ids]
    kept = len([row for row in rows if row[2] and row[0] not in explained_ids])
    cr.execute(
        f"""
        SELECT COUNT(*) FROM mail_tracking_value t
        WHERE NOT EXISTS (SELECT 1 FROM {LEGACY_TRACKING_TABLE} l WHERE l.id = t.id)
        """  # noqa: E8103
    )
    created = cr.fetchone()[0]
    _logger.info(
        "tracking rows: before=%s kept=%s dropped with an obsolete model=%s "
        "unexplained=%s created during the run=%s",
        before,
        kept,
        len(explained),
        len(unexplained),
        created,
    )
    if explained:
        _logger.warning(
            "tracking rows dropped with the messages of obsolete models %s: ids %s",
            sorted({row[1] for row in explained}),
            [row[0] for row in explained],
        )
    if before != kept + len(explained):
        _logger.error(
            "UNEXPLAINED tracking rows lost: before=%s != kept=%s + explained=%s; "
            "ids %s",
            before,
            kept,
            len(explained),
            [row[0] for row in unexplained],
        )
    cr.execute(
        f"""
        SELECT COUNT(*) FROM {LEGACY_TRACKING_TABLE} l
        JOIN mail_message m ON m.id = l.mail_message_id
        WHERE m.message_type != 'tracking' OR COALESCE(m.body, '') = ''
        """  # noqa: E8103
    )
    bad = cr.fetchone()[0]
    if bad:
        _logger.error(
            "%s messages with tracking rows are not message_type 'tracking' or "
            "have an empty body",
            bad,
        )


@openupgrade.migrate()
def migrate(env, version):
    _check_tracking_rows(env)
