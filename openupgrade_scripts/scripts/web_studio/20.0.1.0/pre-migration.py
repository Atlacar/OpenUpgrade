# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # CHECK(method IS NOT NULL OR action_id IS NOT NULL) was merged into the
    # constraint method_or_action_together (same name, new definition, recreated
    # by the ORM): drop the removed one
    if openupgrade.table_exists(env.cr, "studio_approval_rule"):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE studio_approval_rule
            DROP CONSTRAINT IF EXISTS studio_approval_rule_method_or_action_not_null
            """,
        )
