# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_deleted_xmlids = [
    # wave transfers are numbered with the batch sequence in Odoo 20
    "stock.seq_picking_wave",
]


def _convert_scrap_reason_tags(env):
    """stock.scrap.scrap_reason_tag_ids -> stock.move.scrap_reason_tag_ids"""
    cr = env.cr
    if not (
        openupgrade.table_exists(cr, "stock_scrap_stock_scrap_reason_tag_rel")
        and openupgrade.column_exists(cr, "stock_move", "scrap_id")
    ):
        return
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO stock_move_stock_scrap_reason_tag_rel
            (stock_move_id, stock_scrap_reason_tag_id)
        SELECT m.id, rel.stock_scrap_reason_tag_id
        FROM stock_scrap_stock_scrap_reason_tag_rel rel
        JOIN stock_move m ON m.scrap_id = rel.stock_scrap_id
        ON CONFLICT DO NOTHING
        """,
    )


def _compute_move_quantity_product_uom(env):
    """Moves whose uom is not the product uom were left NULL in pre-migration"""
    cr = env.cr
    cr.execute("SELECT id FROM stock_move WHERE quantity_product_uom IS NULL")
    move_ids = [row[0] for row in cr.fetchall()]
    if move_ids:
        moves = env["stock.move"].browse(move_ids)
        moves._compute_quantity_product_uom()
        moves.flush_recordset(["quantity_product_uom"])


@openupgrade.migrate()
def migrate(env, version):
    _convert_scrap_reason_tags(env)
    _compute_move_quantity_product_uom(env)
    openupgrade.load_data(env, "stock", "20.0.1.1/noupdate_changes.xml")
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
