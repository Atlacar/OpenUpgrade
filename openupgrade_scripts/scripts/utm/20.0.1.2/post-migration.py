# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "utm", "20.0.1.2/noupdate_changes.xml")
    # generic mediums/sources removed from the data in 20.0 (noupdate records are
    # not removed by the ORM): not used in prod, delete when not referenced
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "utm.utm_medium_banner",
            "utm.utm_medium_facebook",
            "utm.utm_medium_google_adwords",
            "utm.utm_medium_linkedin",
            "utm.utm_medium_television",
            "utm.utm_medium_twitter",
            "utm.utm_source_search_engine",
        ],
    )
