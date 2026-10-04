# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from lxml import etree
from openupgradelib import openupgrade

# pylint: disable=odoo-addons-relative-import
from odoo.addons.openupgrade_scripts.apriori import merged_modules, renamed_modules
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

# xmlids that were renamed in the 20.0 data files of base with identical
# code/name (diff of res.country.state.csv 19.0 vs 20.0): without the rename the
# 20.0 record is created as a new one and violates unique(country_id, code)
_renamed_xmlids = [
    # Odisha: state_in_or (19.0) -> state_in_od (20.0), same code OD
    ("base.state_in_or", "base.state_in_od"),
    # the model website (and its default record) moved from the website module
    # to base
    ("website.default_website", "base.default_website"),
    (
        "website.constraint_website_domain_unique",
        "base.constraint_website_domain_unique",
    ),
]

_renamed_fields = [
    ("res.partner.bank", "res_partner_bank", "acc_number", "account_number"),
    (
        "res.partner.bank",
        "res_partner_bank",
        "sanitized_acc_number",
        "sanitized_account_number",
    ),
    ("res.partner.bank", "res_partner_bank", "acc_holder_name", "holder_name"),
]

# fields of the model website that are defined in base in 20.0 (were in the
# website module in 19.0)
_website_base_fields = [
    "id",
    "display_name",
    "name",
    "sequence",
    "user_id",
    "company_id",
    "domain",
    "domain_punycode",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
]


def _stash_access_xmlids(env):
    """ir.model.access and ir.rule are replaced by ir.access. Almost all their
    xmlids are reused by ir.access records with the same name coming from the
    ir.access.csv/xml files of the 20.0 modules. Loading such a record fails
    ("found record of different model") if the old xmlid still exists, so:

    * keep a copy of the xmlids (module, name, model, res_id, noupdate) in a
      legacy table, used in post-migration to find out which old records are
      not module-defined (custom, Studio, user-created: they are converted to
      ir.access rows, the module-defined ones are reloaded from the 20.0 files)
    * drop the xmlids of both models, for all modules.
    The old tables ir_model_access and ir_rule are left untouched (the
    openupgrade framework never drops tables/columns)."""
    cr = env.cr
    legacy = openupgrade.get_legacy_name("ir_access_xmlid")
    if not openupgrade.table_exists(cr, legacy):
        openupgrade.logged_query(
            cr,
            f"""
            CREATE TABLE {legacy} AS (
                SELECT model, res_id, module, name, noupdate
                FROM ir_model_data
                WHERE model IN ('ir.model.access', 'ir.rule')
            )
            """,
        )
    openupgrade.logged_query(
        cr, "DELETE FROM ir_model_data WHERE model IN ('ir.model.access', 'ir.rule')"
    )


def _website_moved_to_base(env):
    """The model website, with its fields name, sequence, user_id, company_id,
    domain, domain_punycode, and its unique(domain) constraint, is now defined in
    base (the website module only extends it). Move the xmlids of the fields and
    of the constraint, otherwise the website module cleanup would delete them.
    The xmlid of the default record is renamed in _renamed_xmlids."""
    cr = env.cr
    openupgrade.update_module_moved_fields(
        cr, "website", _website_base_fields, "website", "base"
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_constraint c
        SET module = base.id
        FROM ir_model m, ir_module_module base
        WHERE m.id = c.model AND m.model = 'website'
            AND c.name = 'website_domain_unique'
            AND base.name = 'base'
            AND c.module != base.id
        """,
    )


def _contact_address_inline_moved_to_base(env):
    """res.partner/res.users.contact_address_inline (not stored) was defined in the
    mail module, it is now defined in base."""
    for model in ("res.partner", "res.users"):
        openupgrade.update_module_moved_fields(
            env.cr, model, ["contact_address_inline"], "mail", "base"
        )


def _res_partner_bank(env):
    """res.bank is removed, its data is denormalized in res.partner.bank (bank_name,
    bank_bic, street, street2, zip, city, state_id, country_id). The columns are
    pre-created and filled here to avoid that the computed (precompute) fields
    country_id and clearing_label_id are calculated by the ORM against records that
    are not loaded yet (clearing.label data)."""
    cr = env.cr
    openupgrade.rename_fields(env, _renamed_fields)
    openupgrade.add_columns(
        env,
        [
            ("res.partner.bank", "bank_name", "char", None, "res_partner_bank"),
            ("res.partner.bank", "street", "char", None, "res_partner_bank"),
            ("res.partner.bank", "street2", "char", None, "res_partner_bank"),
            ("res.partner.bank", "zip", "char", None, "res_partner_bank"),
            ("res.partner.bank", "city", "char", None, "res_partner_bank"),
            ("res.partner.bank", "state_id", "many2one", None, "res_partner_bank"),
            ("res.partner.bank", "country_id", "many2one", None, "res_partner_bank"),
            (
                "res.partner.bank",
                "clearing_label_id",
                "many2one",
                None,
                "res_partner_bank",
            ),
        ],
    )
    # bank_bic was a related (not stored) field: add the column
    openupgrade.add_columns(
        env, [("res.partner.bank", "bank_bic", "char", None, "res_partner_bank")]
    )
    if openupgrade.table_exists(cr, "res_bank") and openupgrade.column_exists(
        cr, "res_partner_bank", "bank_id"
    ):
        openupgrade.logged_query(
            cr,
            """
            UPDATE res_partner_bank rpb
            SET bank_name = rb.name,
                bank_bic = rb.bic,
                street = rb.street,
                street2 = rb.street2,
                zip = rb.zip,
                city = rb.city,
                state_id = rb.state,
                country_id = rb.country
            FROM res_bank rb
            WHERE rb.id = rpb.bank_id
            """,
        )
    # country_id: same fallbacks as _compute_country_id (partner, company, main
    # company)
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_partner_bank rpb
        SET country_id = COALESCE(
            (SELECT p.country_id FROM res_partner p WHERE p.id = rpb.partner_id),
            (
                SELECT cp.country_id
                FROM res_company co JOIN res_partner cp ON cp.id = co.partner_id
                WHERE co.id = rpb.company_id
            ),
            (
                SELECT cp.country_id
                FROM res_company co JOIN res_partner cp ON cp.id = co.partner_id
                ORDER BY co.id LIMIT 1
            )
        )
        WHERE rpb.country_id IS NULL
        """,
    )
    _clearing_labels(env)
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_partner_bank rpb
        SET clearing_label_id = COALESCE(
            (
                SELECT cl.id FROM clearing_label cl
                WHERE cl.country_id = rpb.country_id ORDER BY cl.id LIMIT 1
            ),
            (
                SELECT cl.id FROM clearing_label cl
                WHERE cl.country_id IS NULL ORDER BY cl.id LIMIT 1
            )
        )
        """,
    )


def _clearing_labels(env):
    """clearing.label is a new model whose records (data/clearing_label_data.xml)
    are needed by the required field res.partner.bank.clearing_label_id. Create
    the table and the records now (with their xmlids, so that the 20.0 data load
    just updates them), read from the data file of the 20.0 base module."""
    cr = env.cr
    if not openupgrade.table_exists(cr, "clearing_label"):
        openupgrade.logged_query(
            cr,
            """
            CREATE TABLE clearing_label (
                id SERIAL NOT NULL PRIMARY KEY,
                name VARCHAR NOT NULL,
                country_id INTEGER REFERENCES res_country(id) ON DELETE SET NULL,
                create_uid INTEGER,
                create_date TIMESTAMP WITHOUT TIME ZONE,
                write_uid INTEGER,
                write_date TIMESTAMP WITHOUT TIME ZONE
            )
            """,
        )
    with file_open("base/data/clearing_label_data.xml", "rb") as fp:
        tree = etree.parse(fp)
    for record in tree.xpath("//record[@model='clearing.label']"):
        xmlid = record.get("id")
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = 'base' AND name = %s",
            (xmlid,),
        )
        if cr.fetchone():
            continue
        name = record.xpath("field[@name='name']")[0].text
        country_ref = record.xpath("field[@name='country_id']/@ref")
        country_id = None
        if country_ref:
            ref = country_ref[0].split(".")[-1]
            cr.execute(
                """
                SELECT res_id FROM ir_model_data
                WHERE module = 'base' AND name = %s AND model = 'res.country'
                """,
                (ref,),
            )
            row = cr.fetchone()
            if not row:
                continue
            country_id = row[0]
        cr.execute(
            """
            INSERT INTO clearing_label (name, country_id, create_uid, create_date,
                write_uid, write_date)
            VALUES (%s, %s, 1, now() at time zone 'UTC', 1, now() at time zone 'UTC')
            RETURNING id
            """,
            (name, country_id),
        )
        openupgrade.add_xmlid(cr, "base", xmlid, "clearing.label", cr.fetchone()[0])


def _legacy_columns(env):
    """Data of fields removed in 20.0 that has no successor is copied to legacy
    columns (openupgrade.get_legacy_name) so that the values survive in the
    migrated database:
    - res.partner.bank.currency_id (prod: 9 rows, all MXN)
    - ir.actions.report.report_file (prod: 60 of 62 rows)
    - res.company.layout_background ('Blank' in prod; 20.0 has no report background
      at all, which is what 'Blank' meant; 'Demo logo' / 'Custom' have no 20.0
      equivalent, the value is kept in the legacy column and logged)
    """
    cr = env.cr
    openupgrade.copy_columns(
        cr,
        {
            "res_partner_bank": [("currency_id", None, None)],
            "ir_act_report_xml": [("report_file", None, None)],
            "res_company": [("layout_background", None, None)],
        },
    )
    legacy = openupgrade.get_legacy_name("layout_background")
    cr.execute(
        f"""
        SELECT id, name, {legacy} FROM res_company
        WHERE {legacy} IS NOT NULL AND {legacy} != 'Blank'
        """
    )
    for company_id, name, value in cr.fetchall():
        _logger.warning(
            "Company %s (id %s) used the report background %r: Odoo 20.0 has no "
            "report background, the value is kept in column %s.",
            name,
            company_id,
            value,
            legacy,
        )


def _res_country_zip_applicability(env):
    """res.country.zip_required (boolean) -> zip_applicability (selection, required).
    True -> required, False -> optional (zip was displayed but not required). The
    countries whose upstream data changed (not applicable / optional) are updated in
    post-migration from noupdate_changes.xml."""
    cr = env.cr
    openupgrade.add_columns(
        env, [("res.country", "zip_applicability", "selection", None, "res_country")]
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_country
        SET zip_applicability = CASE
            WHEN zip_required IS FALSE THEN 'optional' ELSE 'required' END
        WHERE zip_applicability IS NULL
        """,
    )


def _res_company(env):
    cr = env.cr
    # layout_background (required, no default in 20.0) was removed
    cr.execute(
        """
        SELECT is_nullable FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = 'layout_background'
        """
    )
    row = cr.fetchone()
    if row and row[0] == "NO":
        openupgrade.logged_query(
            cr, "ALTER TABLE res_company ALTER COLUMN layout_background DROP NOT NULL"
        )
    # font: Fira_Mono removed, Noto_Sans_Mono added (monospace replacement)
    openupgrade.logged_query(
        cr, "UPDATE res_company SET font = 'Noto_Sans_Mono' WHERE font = 'Fira_Mono'"
    )


def _ir_model_fields_index(env):
    """ir.model.fields.index: boolean -> selection (btree, btree_not_null, trigram).
    The ORM would cast the boolean column to 'true'/'false' strings: do it here,
    True -> 'btree', False -> NULL (same as IrModelFields._reflect_field)."""
    cr = env.cr
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'ir_model_fields' AND column_name = 'index'
        """
    )
    row = cr.fetchone()
    if row and row[0] == "boolean":
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE ir_model_fields
            ALTER COLUMN "index" TYPE VARCHAR
            USING (CASE WHEN "index" THEN 'btree' ELSE NULL END)
            """,
        )


def _ir_act_client_params_store(env):
    """ir.actions.client.params_store: binary (bytea holding the repr of a dict) ->
    text. A plain cast would give the hex representation of the bytes."""
    cr = env.cr
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'ir_act_client' AND column_name = 'params_store'
        """
    )
    row = cr.fetchone()
    if row and row[0] == "bytea":
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE ir_act_client
            ALTER COLUMN params_store TYPE TEXT
            USING convert_from(params_store, 'UTF8')
            """,
        )


def _res_device_log(env):
    """res.device.log stores the raw user agent (required) instead of
    platform/browser/device_type, user_id is a plain integer (no foreign key, to
    keep the reference of deleted users) and ip_address, first_activity and
    last_activity are required."""
    cr = env.cr
    openupgrade.add_columns(
        env, [("res.device.log", "user_agent", "char", None, "res_device_log")]
    )
    if openupgrade.column_exists(cr, "res_device_log", "platform"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE res_device_log
            SET user_agent = COALESCE(
                NULLIF(CONCAT_WS(' ', platform, browser), ''), 'Unknown'
            )
            WHERE user_agent IS NULL
            """,
        )
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_device_log
        SET user_agent = COALESCE(user_agent, 'Unknown'),
            ip_address = COALESCE(ip_address, ''),
            first_activity = COALESCE(
                first_activity, last_activity, create_date, now() at time zone 'UTC'
            ),
            last_activity = COALESCE(
                last_activity, first_activity, create_date, now() at time zone 'UTC'
            )
        WHERE user_agent IS NULL OR ip_address IS NULL
            OR first_activity IS NULL OR last_activity IS NULL
        """,
    )
    openupgrade.logged_query(cr, "DELETE FROM res_device_log WHERE user_id IS NULL")
    openupgrade.logged_query(
        cr,
        "ALTER TABLE res_device_log "
        "DROP CONSTRAINT IF EXISTS res_device_log_user_id_fkey",
    )


def _res_groups_name_uniq(env):
    """The unique(privilege_id, name) constraint of res.groups was removed."""
    openupgrade.logged_query(
        env.cr, "ALTER TABLE res_groups DROP CONSTRAINT IF EXISTS res_groups_name_uniq"
    )


def _drop_merged_modules_without_target(env):
    """Merged modules whose target is not installed and that own no data.

    ``update_module_names(merge_modules=True)`` hands the *state* of the old module
    to a not installed merge target. ``iot_base`` (assets only, no model, no
    xmlid) is merged into ``iot``: renaming it would leave ``iot`` installed,
    which drags ``printer`` and every ``*_iot`` auto-install bridge into a database
    without any IoT device. When the target is not installed and the old module
    owns no ir_model_data (other than its own module record in base), the old
    module row is dropped instead (nothing to move). Returns the merges left to
    apply with ``update_module_names``."""
    cr = env.cr
    remaining = {}
    for old_name, new_name in merged_modules.items():
        cr.execute("SELECT id FROM ir_module_module WHERE name = %s", [old_name])
        old = cr.fetchone()
        cr.execute("SELECT state FROM ir_module_module WHERE name = %s", [new_name])
        target = cr.fetchone()
        target_installed = bool(
            target and target[0] in ("installed", "to install", "to upgrade")
        )
        if not old or target_installed:
            remaining[old_name] = new_name
            continue
        cr.execute("SELECT count(*) FROM ir_model_data WHERE module = %s", [old_name])
        if cr.fetchone()[0]:
            _logger.warning(
                "Merged module %s owns data but its target %s is not installed: "
                "applying the normal merge",
                old_name,
                new_name,
            )
            remaining[old_name] = new_name
            continue
        _logger.info(
            "Merged module %s owns no data and its target %s is not installed: "
            "dropping the module record instead of installing the target",
            old_name,
            new_name,
        )
        openupgrade.logged_query(
            cr, "DELETE FROM ir_module_module_dependency WHERE module_id = %s", [old[0]]
        )
        openupgrade.logged_query(
            cr, "DELETE FROM ir_module_module_dependency WHERE name = %s", [old_name]
        )
        openupgrade.logged_query(
            cr,
            "DELETE FROM ir_model_data WHERE module = 'base' "
            "AND model = 'ir.module.module' AND name = %s",
            ["module_%s" % old_name],
        )
        for table in ("ir_model_constraint", "ir_model_relation"):
            openupgrade.logged_query(
                cr, f"DELETE FROM {table} WHERE module = %s", [old[0]]
            )
        openupgrade.logged_query(
            cr, "DELETE FROM ir_module_module WHERE id = %s", [old[0]]
        )
    return remaining


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(
        env.cr,
        f"""
        CREATE TABLE {
            openupgrade.get_legacy_name("ir_module_module")
        } AS (SELECT name, state FROM ir_module_module);
        """,
    )
    openupgrade.update_module_names(
        env.cr, renamed_modules.items(), environment_namespec=True
    )
    openupgrade.update_module_names(
        env.cr,
        _drop_merged_modules_without_target(env).items(),
        merge_modules=True,
        environment_namespec=True,
    )
    openupgrade.clean_transient_models(env.cr)
    _stash_access_xmlids(env)
    openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
    _website_moved_to_base(env)
    _contact_address_inline_moved_to_base(env)
    _legacy_columns(env)
    _res_partner_bank(env)
    _res_country_zip_applicability(env)
    _res_company(env)
    _ir_model_fields_index(env)
    _ir_act_client_params_store(env)
    _res_device_log(env)
    _res_groups_name_uniq(env)
