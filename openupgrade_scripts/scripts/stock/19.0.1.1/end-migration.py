# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tools import html2plaintext, is_html_empty
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


def _18_default_descriptions(move):
    """What 18 wrote on the move by itself (stock_rule._get_stock_move_values,
    product._get_description, purchase_stock): such a value is no manual edit,
    and keeping it would stop 19 from merging new moves into this one."""
    product = move.product_id.with_context(lang=move._get_lang())
    code = move.picking_type_id.code
    text = (
        html2plaintext(product.description)
        if not is_html_empty(product.description)
        else product.name
    )
    if code == "incoming":
        default = product.description_pickingin or text
    elif code == "outgoing":
        default = product.description_pickingout or product.name
    elif code == "internal":
        default = product.description_picking or text
    else:
        default = text
    defaults = {default}
    sale_line = move.sudo().sale_line_id if "sale_line_id" in move._fields else False
    if sale_line:
        variants = sale_line.with_context(
            lang=sale_line.order_id.partner_id.lang
        )._get_sale_order_line_multiline_description_variants()
        if variants.strip():
            defaults.add(default + variants)
    purchase_line = (
        move.sudo().purchase_line_id if "purchase_line_id" in move._fields else False
    )
    if purchase_line:
        defaults.add(product.description_pickingin or purchase_line.name)
    return defaults


def _keep_description_picking(env):
    """18 stored stock.move#description_picking as written on the move (vendor
    product name, manual edits, product name at the time); 19 computes it from
    the current product unless description_picking_manual is set. Keep the 18
    value where it differs from the 19 one and is not what 18 wrote by default.
    Runs here so that every override of _compute_description_picking
    (purchase_stock, sale_stock, mrp...) is loaded."""
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
            and batch[move.id] not in _18_default_descriptions(move)
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
