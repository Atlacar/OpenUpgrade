# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_MIGRATION_DESCRIPTION = "Balance carried over from the previous version"


def loyalty_history_split_issued_and_used(env):
    """In 20.0 a history line either awards (issued) or consumes (used) points
    (constraint issued_or_used). Split the lines that did both.
    """
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO loyalty_history (
            card_id, description, issued, used, points_changed_date,
            order_model, order_id, create_uid, create_date, write_uid, write_date
        )
        SELECT
            card_id, description, 0, used, points_changed_date,
            order_model, order_id, create_uid, create_date, write_uid, write_date
        FROM loyalty_history
        WHERE issued > 0 AND used > 0
        """,
    )
    openupgrade.logged_query(
        env.cr,
        "UPDATE loyalty_history SET used = 0 WHERE issued > 0 AND used > 0",
    )


def loyalty_card_points(env):
    """loyalty.card#points is no longer stored but computed from the history
    lines (issued - used). Add a balancing history line for the cards whose
    history does not match the stored balance, so no points are lost.
    """
    if not openupgrade.column_exists(env.cr, "loyalty_card", "points"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO loyalty_history (
            card_id, description, issued, used, points_changed_date,
            create_date, write_date
        )
        SELECT
            card.id, %(description)s,
            GREATEST(card.points - COALESCE(h.balance, 0), 0),
            GREATEST(COALESCE(h.balance, 0) - card.points, 0),
            NOW() AT TIME ZONE 'UTC',
            NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
        FROM loyalty_card card
        LEFT JOIN (
            SELECT card_id, SUM(COALESCE(issued, 0) - COALESCE(used, 0)) AS balance
            FROM loyalty_history
            GROUP BY card_id
        ) h ON h.card_id = card.id
        WHERE ABS(COALESCE(card.points, 0) - COALESCE(h.balance, 0)) > 0.000001
        """,
        {"description": _MIGRATION_DESCRIPTION},
    )


@openupgrade.migrate()
def migrate(env, version):
    loyalty_history_split_issued_and_used(env)
    loyalty_card_points(env)
