# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _external_layout_to_table_design(env):
    """The external layouts bold, boxed and striped are removed: they became the
    "table design" (res.company.report_tables_id) of the standard layout."""
    cr = env.cr
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
        WHERE module = 'web' AND name = 'external_layout_standard'
            AND model = 'ir.ui.view'
        """
    )
    row = cr.fetchone()
    if not row:
        return
    standard_id = row[0]
    for design in ("bold", "boxed", "striped"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE res_company c
            SET external_report_layout_id = %s, report_tables_id = %s
            FROM ir_model_data d
            WHERE d.module = 'web' AND d.name = %s AND d.model = 'ir.ui.view'
                AND c.external_report_layout_id = d.res_id
            """,
            (standard_id, design, "external_layout_%s" % design),
        )


@openupgrade.migrate()
def migrate(env, version):
    _external_layout_to_table_design(env)
