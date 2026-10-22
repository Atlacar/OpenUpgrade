# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _res_company_tax_return(env):
    """18 tax closing settings of res.company are the tax return settings in 19"""
    if not openupgrade.column_exists(env.cr, "res_company", "account_tax_periodicity"):
        return
    env.cr.execute(
        """
        UPDATE res_company
        SET account_return_periodicity = account_tax_periodicity,
        account_return_reminder_day = account_tax_periodicity_reminder_day,
        account_tax_return_journal_id = COALESCE(
            account_tax_return_journal_id, account_tax_periodicity_journal_id
        )
        """
    )


def _account_return_type_deadline_start_date(env):
    """
    account.report#tax_closing_start_date (company dependent) became
    account.return.type#deadline_start_date (company dependent): carry over the
    defaults and the values of the reports the return types are made of
    """
    env.cr.execute(
        """
        SELECT d.company_id, d.user_id, d.condition, d.json_value
        FROM ir_default d
        JOIN ir_model_fields f ON f.id = d.field_id
        WHERE f.model = 'account.report' AND f.name = 'tax_closing_start_date'
        """
    )
    IrDefault = env["ir.default"]
    for company_id, user_id, condition, json_value in env.cr.fetchall():
        IrDefault.create(
            {
                "field_id": env["ir.model.fields"]
                ._get("account.return.type", "deadline_start_date")
                .id,
                "company_id": company_id,
                "user_id": user_id,
                "condition": condition,
                "json_value": json_value,
            }
        )
    if not openupgrade.column_exists(
        env.cr, "account_report", "tax_closing_start_date"
    ):
        return
    env.cr.execute(
        """
        SELECT rt.id, v.key::int, v.value
        FROM account_return_type rt
        JOIN account_report r ON r.id = rt.report_id
        CROSS JOIN jsonb_each_text(r.tax_closing_start_date) v
        WHERE v.value IS NOT NULL
        """
    )
    ReturnType = env["account.return.type"]
    for return_type_id, company_id, value in env.cr.fetchall():
        return_type = ReturnType.with_company(company_id).browse(return_type_id)
        if not return_type.deadline_start_date:
            return_type.deadline_start_date = value


@openupgrade.migrate()
def migrate(env, version):
    _res_company_tax_return(env)
    _account_return_type_deadline_start_date(env)
