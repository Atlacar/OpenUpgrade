# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_renamed_fields = [
    # same rename as stock.move.location_final_id -> forecasted_location_id
    (
        "purchase.order.line",
        "purchase_order_line",
        "location_final_id",
        "forecasted_location_id",
    ),
]


def _fill_line_date_promised(env):
    """purchase.order.line.date_promised is new: it is set to the planned date
    when the line is confirmed (see purchase_stock _set_date_promised). Do the
    same for the lines of the already confirmed orders; the date promised of the
    order is then computed (minimum of its lines) by the ORM."""
    openupgrade.add_fields(
        env,
        [
            (
                "date_promised",
                "purchase.order.line",
                "purchase_order_line",
                "datetime",
                False,
                "purchase_stock",
            )
        ],
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE purchase_order_line pol
        SET date_promised = pol.date_planned
        FROM purchase_order po
        WHERE po.id = pol.order_id AND po.state = 'purchase'
            AND pol.display_type IS NULL AND pol.date_promised IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _renamed_fields)
    _fill_line_date_promised(env)
