# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

# xmlid modules of records that are not defined by a module (custom accesses)
CUSTOM_XMLID_MODULES = ("__export__", "studio_customization", "__custom__")


def _operation(perm_create, perm_read, perm_write, perm_unlink):
    """Return the ir.access.operation (a subset of 'crud', in that order)"""
    return "".join(
        letter
        for flag, letter in (
            (perm_create, "c"),
            (perm_read, "r"),
            (perm_write, "u"),
            (perm_unlink, "d"),
        )
        if flag
    )


def build_access_rows(acls, rules, everyone_group_id):
    """Compute the ir.access rows replacing custom ir.model.access and ir.rule rows.

    Semantics of Odoo 20 (base/models/ir_access.py): an access with a group is a
    permission (permissions of the groups of a user are OR-ed, each one with its own
    domain), an access without group is a restriction (restrictions are AND-ed).

    * ir.model.access without group (granted to everybody in 19.0): permission of
      the group base.group_everyone.
    * ir.model.access with group: permission of the group, without domain.
    * global ir.rule (no group): restriction, same domain and operations.
    * ir.rule with groups: in 19.0 the rule limits the records of the operations it
      covers for the users of the group, while the ir.model.access gives the right
      to operate. In 20.0 both are the same record: the permission of the group
      is split in the operations covered by a rule (one row per rule, with its
      domain), and the operations not covered (plain row). A group rule without
      custom ir.model.access for the same model and group cannot be expressed
      (the ir.model.access, if any, is defined by a module and reloaded from the
      module data): it is created inactive for manual review, to not widen the
      access silently.

    :param acls: list of dicts with keys id, name, model_id, group_id, perm_*, active
    :param rules: list of dicts with keys id, name, model_id, domain_force, perm_*,
        active, group_ids
    :return: list of dicts: name, model_id, group_id, operation, domain, active,
        sources (list of (old model, old id)), note
    """
    result = []
    # (model_id, group_id) -> list of rows built from custom accesses
    plain_by_key = {}
    for acl in acls:
        operation = _operation(
            acl["perm_create"], acl["perm_read"], acl["perm_write"], acl["perm_unlink"]
        )
        if not operation:
            continue  # grants nothing: no equivalent needed
        group_id = acl["group_id"] or everyone_group_id
        row = {
            "name": acl["name"],
            "model_id": acl["model_id"],
            "group_id": group_id,
            "operation": operation,
            "domain": False,
            "active": acl["active"],
            "sources": [("ir.model.access", acl["id"])],
            "note": False,
        }
        result.append(row)
        plain_by_key.setdefault((acl["model_id"], group_id), []).append(row)

    group_rules = {}
    for rule in rules:
        operation = _operation(
            rule["perm_create"],
            rule["perm_read"],
            rule["perm_write"],
            rule["perm_unlink"],
        )
        if not operation:
            continue
        name = rule["name"] or "Rule %s" % rule["id"]
        if not rule["group_ids"]:
            result.append(
                {
                    "name": name,
                    "model_id": rule["model_id"],
                    "group_id": False,
                    "operation": operation,
                    "domain": rule["domain_force"] or False,
                    "active": rule["active"],
                    "sources": [("ir.rule", rule["id"])],
                    "note": False,
                }
            )
            continue
        for group_id in rule["group_ids"]:
            group_rules.setdefault((rule["model_id"], group_id), []).append(
                (rule, name, operation)
            )

    for key, key_rules in group_rules.items():
        model_id, group_id = key
        plains = plain_by_key.get(key)
        if not plains:
            for rule, name, operation in key_rules:
                result.append(
                    {
                        "name": name,
                        "model_id": model_id,
                        "group_id": group_id,
                        "operation": operation,
                        "domain": rule["domain_force"] or False,
                        "active": False,
                        "sources": [("ir.rule", rule["id"])],
                        "note": (
                            "Migrated from the group record rule #%s: no custom "
                            "access right exists for this group and model, review "
                            "and activate if needed." % rule["id"]
                        ),
                    }
                )
            continue
        covered = set("".join(operation for _r, _n, operation in key_rules))
        for plain in plains:
            ops = set(plain["operation"])
            unrestricted = ops - covered
            restricted_rows = []
            for rule, name, operation in key_rules:
                restricted = ops & set(operation)
                if restricted:
                    restricted_rows.append(
                        {
                            "name": name,
                            "model_id": model_id,
                            "group_id": group_id,
                            "operation": "".join(c for c in "crud" if c in restricted),
                            "domain": rule["domain_force"] or False,
                            "active": plain["active"] and rule["active"],
                            "sources": [("ir.rule", rule["id"])],
                            "note": False,
                        }
                    )
            if unrestricted:
                plain["operation"] = "".join(c for c in "crud" if c in unrestricted)
            elif restricted_rows:
                # the plain row is fully covered by rules: it is replaced by the
                # first restricted one (keeps the xmlid of the access right)
                first = restricted_rows.pop(0)
                first["sources"] = plain["sources"] + first["sources"]
                plain.update(first)
            else:  # pragma: no cover
                continue
            result.extend(restricted_rows)
    return result


def _custom_ids(cr, old_model, table):
    """ids of the records of the old model (ir.model.access or ir.rule) that are not
    defined by a module (no xmlid, or xmlid of a custom module)"""
    legacy = openupgrade.get_legacy_name("ir_access_xmlid")
    cr.execute(
        f"""
        SELECT t.id FROM {table} t
        WHERE NOT EXISTS (
            SELECT 1 FROM {legacy} l
            WHERE l.model = %s AND l.res_id = t.id AND l.module NOT IN %s
        )
        ORDER BY t.id
        """,
        (old_model, CUSTOM_XMLID_MODULES),
    )
    return [row[0] for row in cr.fetchall()]


def _custom_accesses_to_ir_access(env):
    """ir.model.access and ir.rule rows that are not defined in a module (created
    by users or by Studio) are converted to ir.access rows. The ones defined by a
    module are not converted: their xmlids were dropped in pre-migration and the
    20.0 module data (ir.access.csv/xml) creates the new ir.access records."""
    cr = env.cr
    legacy = openupgrade.get_legacy_name("ir_access_xmlid")
    if not openupgrade.table_exists(cr, legacy):
        _logger.warning("No legacy table %s: custom accesses not migrated", legacy)
        return
    everyone = env.ref("base.group_everyone").id
    acl_ids = _custom_ids(cr, "ir.model.access", "ir_model_access")
    rule_ids = _custom_ids(cr, "ir.rule", "ir_rule")
    acls = []
    if acl_ids:
        cr.execute(
            """
            SELECT id, name, model_id, group_id, perm_read, perm_write, perm_create,
                perm_unlink, active
            FROM ir_model_access WHERE id IN %s ORDER BY id
            """,
            (tuple(acl_ids),),
        )
        acls = [
            dict(
                zip(
                    (
                        "id",
                        "name",
                        "model_id",
                        "group_id",
                        "perm_read",
                        "perm_write",
                        "perm_create",
                        "perm_unlink",
                        "active",
                    ),
                    row,
                )
            )
            for row in cr.fetchall()
        ]
    rules = []
    if rule_ids:
        cr.execute(
            """
            SELECT r.id, r.name, r.model_id, r.domain_force, r.perm_read,
                r.perm_write, r.perm_create, r.perm_unlink, r.active,
                ARRAY(
                    SELECT g.group_id FROM rule_group_rel g
                    WHERE g.rule_group_id = r.id ORDER BY g.group_id
                )
            FROM ir_rule r WHERE r.id IN %s ORDER BY r.id
            """,
            (tuple(rule_ids),),
        )
        rules = [
            dict(
                zip(
                    (
                        "id",
                        "name",
                        "model_id",
                        "domain_force",
                        "perm_read",
                        "perm_write",
                        "perm_create",
                        "perm_unlink",
                        "active",
                        "group_ids",
                    ),
                    row,
                )
            )
            for row in cr.fetchall()
        ]
    rows = build_access_rows(acls, rules, everyone)
    _logger.info(
        "Converting %s custom ir.model.access and %s custom ir.rule to %s ir.access",
        len(acls),
        len(rules),
        len(rows),
    )
    for row in rows:
        cr.execute(
            """
            INSERT INTO ir_access (name, active, model_id, group_id, operation, domain,
                note, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, now() at time zone 'UTC',
                1, now() at time zone 'UTC')
            RETURNING id
            """,
            (
                row["name"],
                row["active"],
                row["model_id"],
                row["group_id"] or None,
                row["operation"],
                row["domain"] or None,
                row["note"] or None,
            ),
        )
        new_id = cr.fetchone()[0]
        # keep the xmlid of the custom records (Studio, export)
        for old_model, old_id in row["sources"]:
            cr.execute(
                f"""
                SELECT module, name, noupdate FROM {legacy}
                WHERE model = %s AND res_id = %s AND module IN %s
                """,
                (old_model, old_id, CUSTOM_XMLID_MODULES),
            )
            for module, name, noupdate in cr.fetchall():
                openupgrade.add_xmlid(
                    cr, module, name, "ir.access", new_id, noupdate=noupdate
                )
    if rows:
        env["ir.access"]._clear_caches()


def _commercial_company_name(env):
    """commercial_company_name is now stored and related to
    commercial_partner_id.name (it was computed from company_name, which was not
    stored for individuals): align the stored values."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_partner p
        SET commercial_company_name = c.name
        FROM res_partner c
        WHERE c.id = p.commercial_partner_id
            AND p.commercial_company_name IS DISTINCT FROM c.name
        """,
    )


def _api_keys_scope(env):
    """res.users.apikeys.scope is required in 20 and _check_apikey_credentials matches
    `scope = 'rpc'` exactly (19 accepted `scope IS NULL`, a global key, in
    `_check_credentials`): keep the existing keys usable over RPC. aquila: 1 key.
    Also covers the trusted devices table (same column, same requirement)."""
    cr = env.cr
    for table in ("res_users_apikeys", "auth_totp_device"):
        if openupgrade.table_exists(cr, table) and openupgrade.column_exists(
            cr, table, "scope"
        ):
            openupgrade.logged_query(
                cr,
                "UPDATE %s SET scope = 'rpc' WHERE scope IS NULL" % table,  # noqa: E8103
            )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "base", "20.0.1.3/noupdate_changes.xml")
    _custom_accesses_to_ir_access(env)
    _commercial_company_name(env)
    _api_keys_scope(env)
