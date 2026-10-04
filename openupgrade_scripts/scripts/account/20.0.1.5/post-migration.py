# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from collections import defaultdict

from openupgradelib import openupgrade

from odoo.addons.openupgrade_framework import template_tools

_logger = logging.getLogger(__name__)

# account.account#account_type used for the parent accounts created from groups:
# only generic types, no reconcile/unique/journal constraints attached to them.
_PARENT_ACCOUNT_TYPE = {
    "asset": "asset_current",
    "liability": "liability_current",
    "equity": "equity",
    "income": "income",
    "expense": "expense",
    "off_balance": "off_balance",
}


def _parent_account_type(account_type):
    prefix = (account_type or "").split("_")[0]
    return _PARENT_ACCOUNT_TYPE.get(prefix, account_type or "asset_current")


def account_group_to_parent_accounts(env):
    """The model account.group is gone: the account hierarchy is now stored on
    account.account#parent_id (the parent accounts are inactive accounts holding
    the group name and code prefix, see the chart templates of 20.0).

    19.0 account.account#group_id was computed from the code prefix of the account
    (longest matching code_prefix_start / code_prefix_end of the company, then the
    group parent chain). Only the groups that are an ancestor of an existing
    account are converted: the other groups do not hold any data and would only
    bloat the chart of accounts (a chart template reload creates the ones the
    template wants). The external identifiers of the converted groups are moved to
    the new accounts (the 20.0 chart templates use the same names, e.g.
    account.1_account_subgroup_caja), the ones of the other groups are removed so
    that they can not clash with the new account ids of a template reload.
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, "account_group"):
        return
    cr.execute(
        """
        SELECT id, parent_id, company_id, code_prefix_start, code_prefix_end
        FROM account_group
        ORDER BY id
        """
    )
    groups = {
        row[0]: {
            "id": row[0],
            "parent_id": row[1],
            "company_id": row[2],
            "start": row[3] or "",
            "end": row[4] or row[3] or "",
        }
        for row in cr.fetchall()
    }
    if not groups:
        return
    groups_by_company = defaultdict(list)
    for group in groups.values():
        groups_by_company[group["company_id"]].append(group)
    for company_groups in groups_by_company.values():
        company_groups.sort(key=lambda g: (-len(g["start"]), g["id"]))

    # accounts with their code per (root) company
    cr.execute(
        """
        SELECT account.id, account.account_type, kv.key::int, kv.value
        FROM account_account account
        CROSS JOIN LATERAL jsonb_each_text(
            CASE WHEN jsonb_typeof(account.code_store) = 'object'
                THEN account.code_store ELSE '{}'::jsonb END) kv
        WHERE kv.value IS NOT NULL
        ORDER BY kv.value, account.id
        """
    )
    account_rows = cr.fetchall()
    existing_codes = defaultdict(set)
    account_group = {}  # account id -> group id (first company that has a group)
    account_type = {}
    ordered_accounts = {}
    for account_id, a_type, company_id, code in account_rows:
        existing_codes[company_id].add(code)
        account_type.setdefault(account_id, a_type)
        ordered_accounts[account_id] = True
        if account_id in account_group:
            continue
        for group in groups_by_company.get(company_id, []):
            if (
                group["start"]
                and group["start"] <= code[: len(group["start"])]
                and group["end"] >= code[: len(group["end"])]
            ):
                account_group[account_id] = group["id"]
                break

    # groups to convert: ancestors (including the matching group) of an account
    needed = {}
    group_account_type = {}
    for account_id in ordered_accounts:
        group_id = account_group.get(account_id)
        while group_id:
            if group_id not in needed:
                needed[group_id] = groups[group_id]
            group_account_type.setdefault(
                group_id, _parent_account_type(account_type[account_id])
            )
            group_id = groups[group_id]["parent_id"]

    # skip groups whose code is already the code of an account of the company
    skipped = {
        group_id
        for group_id, group in needed.items()
        if group["start"] in existing_codes[group["company_id"]]
    }
    if skipped:
        _logger.warning(
            "account.group ids %s not converted to parent accounts: an account "
            "with the same code exists",
            sorted(skipped),
        )

    def depth(group):
        level = 0
        while group["parent_id"]:
            level += 1
            group = groups[group["parent_id"]]
        return level

    new_account_of_group = {}
    has_reconcile = openupgrade.column_exists(cr, "account_account", "reconcile")
    has_non_trade = openupgrade.column_exists(cr, "account_account", "non_trade")
    has_create_asset = openupgrade.column_exists(cr, "account_account", "create_asset")
    for group in sorted(needed.values(), key=depth):
        if group["id"] in skipped:
            continue
        columns = [
            "account_type",
            "name",
            "code_store",
            "active",
            "create_uid",
            "write_uid",
            "create_date",
            "write_date",
        ]
        values = [
            "%s",
            "(SELECT name FROM account_group WHERE id = %s)",
            "jsonb_build_object(%s::text, %s::text)",
            "FALSE",
            "1",
            "1",
            "now() at time zone 'UTC'",
            "now() at time zone 'UTC'",
        ]
        params = [
            group_account_type[group["id"]],
            group["id"],
            str(group["company_id"]),
            group["start"],
        ]
        if has_reconcile:
            columns.append("reconcile")
            values.append("FALSE")
        if has_non_trade:
            columns.append("non_trade")
            values.append("FALSE")
        if has_create_asset:
            columns.append("create_asset")
            values.append("'no'")
        cr.execute(
            "INSERT INTO account_account ({}) VALUES ({}) RETURNING id".format(
                ", ".join(columns), ", ".join(values)
            ),
            params,
        )
        new_id = cr.fetchone()[0]
        new_account_of_group[group["id"]] = new_id
        cr.execute(
            """
            INSERT INTO account_account_res_company_rel
                (account_account_id, res_company_id)
            VALUES (%s, %s)
            """,
            (new_id, group["company_id"]),
        )
        cr.execute(
            """
            UPDATE ir_model_data
            SET model = 'account.account', res_id = %s
            WHERE model = 'account.group' AND res_id = %s
            """,
            (new_id, group["id"]),
        )

    def converted_ancestor(group_id):
        while group_id:
            if group_id in new_account_of_group:
                return new_account_of_group[group_id]
            group_id = groups[group_id]["parent_id"]
        return None

    for group_id, new_id in new_account_of_group.items():
        parent_new_id = converted_ancestor(groups[group_id]["parent_id"])
        if parent_new_id:
            cr.execute(
                "UPDATE account_account SET parent_id = %s WHERE id = %s",
                (parent_new_id, new_id),
            )
    for account_id, group_id in account_group.items():
        parent_new_id = converted_ancestor(group_id)
        if parent_new_id:
            cr.execute(
                "UPDATE account_account SET parent_id = %s WHERE id = %s",
                (parent_new_id, account_id),
            )
    # the other groups are dropped, remove their xmlids (the table is kept)
    cr.execute("DELETE FROM ir_model_data WHERE model = 'account.group'")
    env["account.account"]._parent_store_compute()
    env["account.account"].invalidate_model()
    _logger.info(
        "%s account.group converted to parent accounts (out of %s groups)",
        len(new_account_of_group),
        len(groups),
    )


def account_report_line_foldability(env):
    """foldable (boolean) -> foldability selection: the lines flagged as foldable
    keep their folding button. For the others the value computed by the ORM is
    kept."""
    legacy = openupgrade.get_legacy_name("foldable")
    if not openupgrade.column_exists(env.cr, "account_report_line", legacy):
        return
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE account_report_line
        SET foldability = 'foldable'
        WHERE {legacy} IS TRUE
        """,
    )


def account_bank_statement_is_statement_posted(env):
    """New flag is_statement_posted defaults to True: statements having a
    draft line move were draft statements."""
    env.cr.execute(
        """
        UPDATE account_bank_statement s
        SET is_statement_posted = FALSE
        WHERE EXISTS (
            SELECT 1
            FROM account_bank_statement_line l
            JOIN account_move m ON m.id = l.move_id
            WHERE l.statement_id = s.id AND m.state = 'draft'
        )
        """
    )


def res_partner_global_location_number(env):
    """account_add_gln is merged in account: the GLN is not stored anymore, it is
    the additional identifier 'EAN_GLN' of the partner."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "res_partner", "global_location_number"):
        return
    if not openupgrade.column_exists(cr, "res_partner", "additional_identifiers"):
        _logger.warning("res_partner.additional_identifiers missing, GLN not migrated")
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_partner
        SET additional_identifiers = COALESCE(additional_identifiers, '{}'::jsonb)
            || jsonb_build_object('EAN_GLN', global_location_number)
        WHERE COALESCE(global_location_number, '') != ''
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    template_tools.load_data_keep_customized(env, "account", "20.0.1.5/noupdate_changes.xml")
    account_group_to_parent_accounts(env)
    account_report_line_foldability(env)
    account_bank_statement_is_statement_posted(env)
    res_partner_global_location_number(env)
