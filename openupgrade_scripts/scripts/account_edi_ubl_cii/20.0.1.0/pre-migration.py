# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade

_field_renames = [
    # Peppol specific naming becomes a generic electronic routing address
    ("res.partner", "res_partner", "peppol_eas", "routing_scheme"),
    ("res.partner", "res_partner", "peppol_endpoint", "routing_endpoint"),
]


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    spec = [
        field
        for field in _field_renames
        if openupgrade.column_exists(cr, field[1], field[2])
        and not openupgrade.column_exists(cr, field[1], field[3])
    ]
    openupgrade.rename_fields(env, spec)
