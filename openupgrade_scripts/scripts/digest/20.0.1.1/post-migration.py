# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "digest", "20.0.1.1/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "digest",
        [
            "digest_mail_layout",
            "digest_mail_main",
            "digest_section_mobile",
            "digest_tool_kpi",
        ],
        ["arch_db"],
    )
