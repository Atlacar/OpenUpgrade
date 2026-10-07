# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _show_expected_quantity_count(env):
    """18: group stock_barcode.group_barcode_show_quantity_count (implied by
    base.group_user by default) shows the expected quantity when counting.
    19: removed, replaced by the ir.config_parameter
    stock.show_expected_quantity_count (default False). Keep it on when the 18
    group still had members (its xmlid is only removed at the end of the update)."""
    env.cr.execute(
        """
        SELECT 1
        FROM ir_model_data imd
        JOIN res_groups_users_rel rel ON rel.gid = imd.res_id
        WHERE imd.module = 'stock_barcode'
          AND imd.name = 'group_barcode_show_quantity_count'
          AND imd.model = 'res.groups'
        LIMIT 1
        """
    )
    if env.cr.fetchone():
        env["ir.config_parameter"].sudo().set_param(
            "stock.show_expected_quantity_count", "True"
        )


@openupgrade.migrate()
def migrate(env, version):
    _show_expected_quantity_count(env)
