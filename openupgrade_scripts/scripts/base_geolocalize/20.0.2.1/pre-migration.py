# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # should_be_geolocalized is a new stored computed field which evaluates to True
    # for every partner that already has coordinates: the new cron would then call
    # the geocoder for all of them. Nothing changed in the addresses, so pre-create
    # the column with False.
    openupgrade.add_columns(
        env,
        [
            (
                "res.partner",
                "should_be_geolocalized",
                "boolean",
                False,
                "res_partner",
            )
        ],
    )
