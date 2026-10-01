# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Not part of the 20 data anymore (no activity of this type in production)
_deleted_xmlids = [
    "hr_skills.mail_activity_data_upload_certification",
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
