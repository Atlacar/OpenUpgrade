# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _keep_sms_confirmation_off(env):
    """stock_sms auto-installed during the migration (not installed in 18, so no
    legacy res_company.stock_move_sms_validation column): its post_init_hook turns
    SMS delivery confirmation on for every company. Keep the 18 behaviour (off)."""
    if openupgrade.column_exists(
        env.cr, "res_company", "stock_move_sms_validation"
    ) or not openupgrade.is_module_installed(env.cr, "stock_sms"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET stock_text_confirmation = FALSE
        WHERE stock_text_confirmation AND stock_confirmation_type = 'sms'
        """,
    )


def _keep_description_picking(env):
    """18 stored stock.move#description_picking as written on the move (vendor
    product name, manual edits, product name at the time); 19 computes it from
    the current product unless description_picking_manual is set. Keep the 18
    value where it differs from the 19 one. Runs here so that every override of
    _compute_description_picking (purchase_stock, sale_stock, mrp...) is loaded."""
    if not openupgrade.column_exists(env.cr, "stock_move", "description_picking"):
        return
    env.cr.execute(
        """
        SELECT id, description_picking
        FROM stock_move
        WHERE description_picking IS NOT NULL AND description_picking != ''
        AND description_picking_manual IS NULL
        ORDER BY id
        """
    )
    rows = env.cr.fetchall()
    kept = 0
    for start in range(0, len(rows), 2000):
        batch = dict(rows[start : start + 2000])
        moves = env["stock.move"].browse(list(batch))
        to_keep = [
            (batch[move.id], move.id)
            for move in moves
            if move.description_picking != batch[move.id]
        ]
        if to_keep:
            env.cr.executemany(
                "UPDATE stock_move SET description_picking_manual = %s WHERE id = %s",
                to_keep,
            )
            kept += len(to_keep)
        env["stock.move"].invalidate_model()
    openupgrade.logger.info(
        "stock.move: kept the 18 description_picking of %s of %s moves",
        kept,
        len(rows),
    )


@openupgrade.migrate()
def migrate(env, version):
    _keep_sms_confirmation_off(env)
    _keep_description_picking(env)
    env["stock.picking"].search(
        [
            ("move_line_ids", "not in", ("done", "cancel")),
        ]
    )._check_entire_pack()
