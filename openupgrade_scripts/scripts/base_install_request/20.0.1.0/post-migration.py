# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # replaced by the QWeb view base_install_request.mail_installation_request_template
    openupgrade.delete_records_safely_by_xml_id(
        env, ["base_install_request.mail_template_base_install_request"]
    )
