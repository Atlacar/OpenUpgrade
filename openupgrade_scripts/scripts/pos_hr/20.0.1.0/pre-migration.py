# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# The v19 access levels become v20 roles. v19 "minimal" employees could not
# create customers, move cash, change pricelist or use customer account payment:
# the closest v20 role is "restrictive". basic -> cashier, advanced -> manager.
# "supervised" is new and has no source.
_renamed_tables = [
    (
        "pos_hr_minimal_employee_hr_employee",
        "pos_hr_restrictive_employee_hr_employee",
    ),
    ("pos_hr_basic_employee_hr_employee", "pos_hr_cashier_employee_hr_employee"),
    ("pos_hr_advanced_employee_hr_employee", "pos_hr_manager_employee_hr_employee"),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_tables(env.cr, _renamed_tables)
