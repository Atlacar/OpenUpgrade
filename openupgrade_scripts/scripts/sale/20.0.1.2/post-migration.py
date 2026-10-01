# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json

from openupgradelib import openupgrade


def product_template_sale_delay(env):
    """Restore the lead time as company dependent value (one entry for each
    company, as the value used to be global). Zero is the field default.
    """
    legacy = openupgrade.get_legacy_name("sale_delay")
    if not openupgrade.column_exists(env.cr, "product_template", legacy):
        return
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE product_template pt
        SET sale_delay = (
            SELECT jsonb_object_agg(company.id::text, pt.{legacy})
            FROM res_company company
        )
        WHERE pt.{legacy} IS NOT NULL AND pt.{legacy} != 0
        """,
    )


def res_company_sale_invoice_policy(env):
    """The default invoicing policy was an ir.default on
    product.template#invoice_policy (setting default_invoice_policy), it is
    now a company setting. Existing products keep their own value.
    """
    env.cr.execute(
        """
        SELECT d.id, d.company_id, d.json_value
        FROM ir_default d
        JOIN ir_model_fields f ON f.id = d.field_id
        WHERE f.model = 'product.template' AND f.name = 'invoice_policy'
            AND d.user_id IS NULL AND d.condition IS NULL
        ORDER BY d.company_id NULLS FIRST
        """
    )
    default_ids = []
    for default_id, company_id, json_value in env.cr.fetchall():
        default_ids.append(default_id)
        try:
            value = json.loads(json_value)
        except (TypeError, ValueError):
            continue
        if value not in ("order", "delivery"):
            continue
        # ordered by company_id NULLS FIRST: global default, then specific ones
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE res_company SET sale_invoice_policy = %s
            WHERE %s::integer IS NULL OR id = %s
            """,
            (value, company_id, company_id),
        )
    if default_ids:
        openupgrade.logged_query(
            env.cr, "DELETE FROM ir_default WHERE id IN %s", (tuple(default_ids),)
        )


def res_company_sale_automatic_invoice(env):
    """config parameter sale.automatic_invoice -> res.company field"""
    env.cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = 'sale.automatic_invoice'"
    )
    row = env.cr.fetchone()
    if not row:
        return
    if (row[0] or "").strip().lower() in ("true", "1"):
        # through the ORM, to synchronize the activation of the cron
        env["res.company"].search([]).write({"sale_automatic_invoice": True})
    openupgrade.logged_query(
        env.cr, "DELETE FROM ir_config_parameter WHERE key = 'sale.automatic_invoice'"
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "sale", "20.0.1.2/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "sale",
        [
            "email_template_edi_sale",
            "email_template_proforma",
            "mail_template_sale_confirmation",
            "mail_template_sale_payment_executed",
        ],
        ["body_html"],
    )
    product_template_sale_delay(env)
    res_company_sale_invoice_policy(env)
    res_company_sale_automatic_invoice(env)
