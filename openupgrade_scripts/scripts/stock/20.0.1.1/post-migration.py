# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.addons.openupgrade_framework import template_tools

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


def _enable_picking_batch_group(env):
    """Databases that had stock_picking_batch installed in 19.0 keep batch, wave
    and cluster transfers: enable the 20.0 setting "Batch, Wave & Cluster
    Transfers" exactly as res.config.settings does (implied_group on
    base.group_user), so that all internal users get stock.group_stock_picking_batch."""
    marker = openupgrade.get_legacy_name("stock_picking_batch_installed")
    if not openupgrade.table_exists(env.cr, marker):
        return
    batch_group = env.ref("stock.group_stock_picking_batch")
    env.ref("base.group_user").write({"implied_ids": [(4, batch_group.id)]})
    openupgrade.logged_query(env.cr, f"DROP TABLE {marker}")


@openupgrade.migrate()
def migrate(env, version):
    _enable_picking_batch_group(env)
    _convert_scrap_reason_tags(env)
    _compute_move_quantity_product_uom(env)
    template_tools.load_data_keep_customized(env, "stock", "20.0.1.1/noupdate_changes.xml")
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
