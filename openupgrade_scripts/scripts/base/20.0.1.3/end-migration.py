# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _ir_actions_report_save_as_attachment(env):
    """ir.actions.report.save_as_attachment (new, only drives the form view): a
    report was saved as attachment when its 'attachment' expression was set. Done
    at the end so that the reports of all the modules are taken into account."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_act_report_xml
        SET save_as_attachment = TRUE
        WHERE attachment IS NOT NULL AND attachment != ''
            AND save_as_attachment IS NOT TRUE
        """,
    )


def _res_partner_is_company(env):
    """res.partner.is_company is a stored computed field in 20.0
    (_compute_is_company: the partner is its own commercial entity and has a real
    VAT, see base/models/res_partner.py). The stored column keeps the 19.0 values
    and the ORM would only recompute them when vat / parent_id change, so the
    result would depend on the next write. Recompute it for ALL partners now (at
    the end, so that localization overrides of _compute_is_company are applied) and
    log every partner whose value changed (owner decision 1: the 12 partners
    without VAT that flip to person are accepted; the validation suite compares
    this list with the allowlist in migration20/reports/is_company_no_vat.csv)."""
    cr = env.cr
    Partner = env["res.partner"].with_context(active_test=False)
    field = Partner._fields["is_company"]
    cr.execute("SELECT id, is_company FROM res_partner")
    before = dict(cr.fetchall())
    partners = Partner.search([])
    env.add_to_compute(field, partners)
    partners.mapped("is_company")
    env.flush_all()
    cr.execute("SELECT id, name, is_company FROM res_partner ORDER BY id")
    changed = 0
    for partner_id, name, value in cr.fetchall():
        old = before.get(partner_id)
        if old is not None and old != value:
            changed += 1
            _logger.info(
                "res.partner is_company changed: id=%s name=%r %s -> %s",
                partner_id,
                name,
                old,
                value,
            )
    _logger.info(
        "res.partner is_company recomputed for %s partners, %s changed",
        len(before),
        changed,
    )


@openupgrade.migrate()
def migrate(env, version):
    _ir_actions_report_save_as_attachment(env)
    _res_partner_is_company(env)
    openupgrade.disable_invalid_filters(env)
