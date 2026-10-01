# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_added_fields = [
    # Stored computed field (primary calendar of the organizer): pre-created
    # so the ORM does not compute it event by event, filled in post-migration
    # when the calendars exist.
    (
        "calendar_id",
        "calendar.event",
        "calendar_event",
        "many2one",
        None,
        "calendar",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.add_fields(env, _added_fields)
