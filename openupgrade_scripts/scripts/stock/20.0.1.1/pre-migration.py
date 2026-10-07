# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_STOCK_QUANTITY_FIELDS = [
    "free_qty",
    "incoming_qty",
    "is_storable",
    "outgoing_qty",
    "qty_available",
    "show_qty_update_button",
    "virtual_available",
]

# (model, fields, new module); the old module is always 'stock'
_moved_fields = [
    # normally already done by the pre-migration of 'product' (loaded before)
    ("product.product", _STOCK_QUANTITY_FIELDS, "product"),
    ("product.template", _STOCK_QUANTITY_FIELDS, "product"),
    ("product.product", ["sale_delay"], "sale"),
    ("product.template", ["sale_delay"], "sale"),
    ("stock.move.line", ["product_category_name"], "stock_barcode"),
]

_renamed_fields = [
    # uom fields were harmonised to uom_id
    ("stock.move", "stock_move", "product_uom", "uom_id"),
    ("stock.move.line", "stock_move_line", "product_uom_id", "uom_id"),
    # the 'final location' of a move is now called the forecasted location
    ("stock.move", "stock_move", "location_final_id", "forecasted_location_id"),
]


_PICKING_BATCH_MARKER = openupgrade.get_legacy_name("stock_picking_batch_installed")


def _move_fields(env, model, fields, old_module, new_module):
    """Move the xmlid of the field definitions to the new module, tolerating
    that the new module reflected the field already (then the stale xmlid of
    the old module is dropped so that the field record and its column survive)."""
    cr = env.cr
    cr.execute(
        """
        SELECT imd.id, imd.name
        FROM ir_model_data imd
        JOIN ir_model_fields imf ON imf.id = imd.res_id
        WHERE imd.model = 'ir.model.fields' AND imd.module = %s
            AND imf.model = %s AND imf.name IN %s
        """,
        (old_module, model, tuple(fields)),
    )
    for imd_id, name in cr.fetchall():
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
            (new_module, name),
        )
        if cr.fetchone():
            openupgrade.logged_query(
                cr, "DELETE FROM ir_model_data WHERE id = %s", (imd_id,)
            )
        else:
            openupgrade.logged_query(
                cr,
                "UPDATE ir_model_data SET module = %s WHERE id = %s",
                (new_module, imd_id),
            )


def _convert_scrap_to_moves(env):
    """stock.scrap is merged into stock.move: a scrap is a stock.move flagged
    is_scrap (with scrap_reason_tag_ids and should_replenish_scrapped). Done
    scraps already own their stock.move (stock_move.scrap_id), so only the flags
    and the user visible data of the scrap have to be carried over. The m2m
    scrap_reason_tag_ids is filled in post-migration."""
    cr = env.cr
    openupgrade.add_fields(
        env,
        [
            ("is_scrap", "stock.move", "stock_move", "boolean", False, "stock", False),
            (
                "should_replenish_scrapped",
                "stock.move",
                "stock_move",
                "boolean",
                False,
                "stock",
                False,
            ),
        ],
    )
    if not (
        openupgrade.table_exists(cr, "stock_scrap")
        and openupgrade.column_exists(cr, "stock_move", "scrap_id")
    ):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE stock_move m
        SET is_scrap = TRUE,
            should_replenish_scrapped = COALESCE(s.should_replenish, FALSE),
            reference = COALESCE(NULLIF(m.reference, ''), s.name),
            origin = COALESCE(m.origin, s.origin),
            picking_id = COALESCE(m.picking_id, s.picking_id)
        FROM stock_scrap s
        WHERE m.scrap_id = s.id
        """,
    )
    # a scrap that was never validated has no move: there is no equivalent in
    # Odoo 20 (the scrap move is created when the scrap is done)
    cr.execute(
        """
        SELECT count(*) FROM stock_scrap s
        WHERE NOT EXISTS (SELECT 1 FROM stock_move m WHERE m.scrap_id = s.id)
        """
    )
    count = cr.fetchone()[0]
    if count:
        openupgrade.logger.warning(
            "%s stock.scrap record(s) without stock.move (draft scrap orders) "
            "are not migrated: stock.scrap does not exist anymore in Odoo 20",
            count,
        )


def _prefill_move_quantity_product_uom(env):
    """stock.move.quantity_product_uom is a new stored computed field: quantity
    expressed in the product uom. Avoid computing 80k moves with the ORM when the
    move uom is the product uom (the vast majority). Moves in another uom stay
    NULL and are computed in post-migration."""
    openupgrade.add_fields(
        env,
        [("quantity_product_uom", "stock.move", "stock_move", "float", False, "stock")],
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE stock_move m
        SET quantity_product_uom = COALESCE(m.quantity, 0)
        FROM product_product pp
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE pp.id = m.product_id AND pt.uom_id = m.uom_id
        """,
    )


def _convert_scrap_reason_tag_color(env):
    """stock.scrap.reason.tag.color: char (hex '#RRGGBB') -> integer (0xRRGGBB)"""
    cr = env.cr
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'stock_scrap_reason_tag' AND column_name = 'color'
        """
    )
    row = cr.fetchone()
    if not row or row[0] == "integer":
        return
    openupgrade.logged_query(
        cr,
        """
        ALTER TABLE stock_scrap_reason_tag ALTER COLUMN color TYPE integer
        USING CASE
            WHEN color ~ '^#[0-9a-fA-F]{6}$'
                THEN ('x' || substr(color, 2))::bit(24)::int
            ELSE 3947580
        END
        """,
    )


def _map_tracking(env):
    """product.template.tracking: the 'none' key does not exist anymore, a
    storable product tracked by quantity only has tracking = False."""
    cr = env.cr
    openupgrade.logged_query(
        cr, "UPDATE product_template SET tracking = NULL WHERE tracking = 'none'"
    )
    # ir.default of the field (the company wide default is still 'none')
    openupgrade.logged_query(
        cr,
        """
        DELETE FROM ir_default d
        USING ir_model_fields f
        WHERE f.id = d.field_id AND f.model = 'product.template'
            AND f.name = 'tracking' AND d.json_value = '"none"'
        """,
    )


def _orphan_repair_picking_type(env):
    """code 'repair_operation' only exists with the `repair` module (uninstalled in
    aquila): the key is outside the 20 selection. 1 unused type (id 10, 0 moves, 0
    pickings): make it an archived internal type instead of leaving an invalid value
    (the xmlid and the sequence stay)."""
    openupgrade.logged_query(
        env.cr,
        "UPDATE stock_picking_type SET code = 'internal', active = FALSE "
        "WHERE code = 'repair_operation'",
    )


def _remember_picking_batch(env):
    """stock_picking_batch is merged into stock in 20.0, where batch transfers are
    only available to stock.group_stock_picking_batch. Its 19.0 table exists here
    (before the stock 20 models are loaded) only if the module was installed: keep
    a marker for the post-migration, which enables the group."""
    if openupgrade.table_exists(env.cr, "stock_picking_batch"):
        openupgrade.logged_query(
            env.cr,
            f"CREATE TABLE IF NOT EXISTS {_PICKING_BATCH_MARKER} (id integer)",
        )


@openupgrade.migrate()
def migrate(env, version):
    _remember_picking_batch(env)
    for model, fields, new_module in _moved_fields:
        _move_fields(env, model, fields, "stock", new_module)
    openupgrade.rename_fields(env, _renamed_fields)
    _convert_scrap_to_moves(env)
    _prefill_move_quantity_product_uom(env)
    _convert_scrap_reason_tag_color(env)
    _map_tracking(env)
    _orphan_repair_picking_type(env)
