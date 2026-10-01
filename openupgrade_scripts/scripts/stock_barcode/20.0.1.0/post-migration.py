# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_deleted_xmlids = [
    # "Scale up" barcode aliases (WH-RECEIPTS, O-BTN.validate...) do not exist
    # anymore in Odoo 20
    "stock_barcode.scale_up_alias_1",
    "stock_barcode.scale_up_alias_2",
    "stock_barcode.scale_up_alias_3",
    "stock_barcode.scale_up_alias_4",
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
