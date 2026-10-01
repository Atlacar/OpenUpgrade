# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade

# the reports menus moved from account_reports to accountant (same names)
_renamed_xmlids = [
    ("account_reports." + name, "accountant." + name)
    for name in (
        "account_reports_audit_menu",
        "menu_action_account_report_balance_sheet",
        "menu_action_account_report_cash_flow",
        "menu_action_account_report_coa",
        "menu_action_account_report_exec_summary",
        "menu_action_account_report_general_ledger",
        "menu_action_account_report_gt",
        "menu_action_account_report_profit_and_loss",
    )
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
