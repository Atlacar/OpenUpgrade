# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# The default booking products are created on demand by the code in 20
# (appointment.type#_get_default_booking_product) and no longer identified by
# an xmlid: remove the demo-like noupdate record if it is not referenced.
_deleted_xmlids = [
    "appointment_account_payment.default_booking_product",
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
