# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # The to-do mail alias moved to the new auto-installed module
    # project_enterprise_hr_todo. Keep the existing row (a second alias with the
    # same name would fail the uniqueness check while the new module loads).
    openupgrade.rename_xmlids(
        env.cr,
        [
            (
                "project_enterprise_hr.mail_alias_todo",
                "project_enterprise_hr_todo.mail_alias_todo",
            )
        ],
    )
