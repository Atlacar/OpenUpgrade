# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _drop_legacy_access_xmlids(env):
    """Odoo 20 replaced ir.model.access and ir.rule by ir.access and often keeps
    the xmlid (e.g. mail.access_mail_template, mail.ir_rule_discuss_channel_all).
    ``_load_records`` raises a ValidationError when an xmlid exists for another
    model, so forget the legacy xmlids of this module. The rows themselves are
    converted (or dropped) by the base script. Defensive: no-op if base already
    did it."""
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'mail' AND model IN ('ir.model.access', 'ir.rule')
        """,
    )


def _tracking_values(env):
    """mail.tracking.value moved from ``mail`` to the new module ``mail_tracking``.

    * currency_id is not a column of the new model anymore: it lives in the json
      field_info (``field_info['currency_id']``), see
      mail_tracking_value._create_mail_tracking_values in Odoo 20.
    * if mail_tracking is going to be installed (forced install, see
      docs/scripts_mail.md), move the model/field xmlids so that the table and
      its 49k rows survive the removal of the obsolete model of ``mail``.
    * else keep a legacy copy of the table: the ORM drops the table of the
      obsolete model at the end of the update.
    The chatter history itself (rendered into mail_message.body) is handled in
    post-migration.
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, "mail_tracking_value"):
        return
    if openupgrade.column_exists(cr, "mail_tracking_value", "currency_id"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE mail_tracking_value
            SET field_info = COALESCE(field_info, '{}'::jsonb)
                || jsonb_build_object('currency_id', currency_id)
            WHERE currency_id IS NOT NULL
            """,
        )
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'mail_tracking'")
    row = cr.fetchone()
    if row and row[0] in ("to install", "installed", "to upgrade"):
        openupgrade.update_module_moved_models(
            cr, "mail.tracking.value", "mail", "mail_tracking"
        )
        openupgrade.update_module_moved_fields(
            cr, "mail.message", ["tracking_value_ids"], "mail", "mail_tracking"
        )
    else:
        _logger.warning(
            "mail_tracking is not selected for installation: keeping a copy of "
            "mail_tracking_value in openupgrade_legacy_20_0_mail_tracking_value"
        )
        openupgrade.logged_query(
            cr,
            """
            CREATE TABLE openupgrade_legacy_20_0_mail_tracking_value AS
            SELECT * FROM mail_tracking_value
            """,
        )


def _drop_not_null_on_removed_fields(env):
    """Removed required fields keep their NOT NULL constraint until the ORM drops
    the column at the very end, which breaks inserts done while loading data."""
    if openupgrade.column_exists(env.cr, "mail_activity_type", "chaining_type"):
        openupgrade.logged_query(
            env.cr,
            "ALTER TABLE mail_activity_type ALTER COLUMN chaining_type DROP NOT NULL",
        )


def _activity_type_suggested_next(env):
    """mail.activity.type.suggested_next_type_ids (m2m) and triggered_next_type_id
    are replaced by the single m2o suggested_next_type_id. Keep one suggestion
    per type (the trigger first). aquila: 0 rows in mail_activity_rel, 0 triggers.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "mail_activity_type", "chaining_type"):
        return
    cr.execute(
        "ALTER TABLE mail_activity_type "
        "ADD COLUMN IF NOT EXISTS suggested_next_type_id integer"
    )
    if openupgrade.column_exists(cr, "mail_activity_type", "triggered_next_type_id"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE mail_activity_type
            SET suggested_next_type_id = triggered_next_type_id
            WHERE chaining_type = 'trigger' AND triggered_next_type_id IS NOT NULL
            """,
        )
    # mail_activity_rel: activity_id suggests recommended_id (same table, same
    # columns as the new previous_type_ids m2m, which therefore stays valid)
    if openupgrade.table_exists(cr, "mail_activity_rel"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE mail_activity_type t
            SET suggested_next_type_id = r.recommended_id
            FROM (
                SELECT activity_id, MIN(recommended_id) AS recommended_id
                FROM mail_activity_rel GROUP BY activity_id
            ) r
            WHERE t.id = r.activity_id AND t.suggested_next_type_id IS NULL
                AND t.chaining_type = 'suggest'
            """,
        )


def _starred_to_bookmarked(env):
    """mail.message.starred_partner_ids -> bookmarked_partner_ids (same columns)"""
    if openupgrade.table_exists(
        env.cr, "mail_message_res_partner_starred_rel"
    ) and not openupgrade.table_exists(
        env.cr, "mail_message_res_partner_bookmarked_rel"
    ):
        openupgrade.rename_tables(
            env.cr,
            [
                (
                    "mail_message_res_partner_starred_rel",
                    "mail_message_res_partner_bookmarked_rel",
                )
            ],
        )


def _channel_member_xmlids(env):
    """Odoo 20 ships noupdate discuss.channel.member records for the admin
    partner in the general and admin channels. The member rows already exist
    on a migrated DB (without xmlid for the admin channel), so give them the
    xmlid before the data file inserts a duplicate (unique channel/partner)."""
    for name, channel_xmlid in (
        ("channel_member_general_channel_for_admin", "channel_all_employees"),
        ("channel_member_channel_admin_partner_admin", "channel_admin"),
    ):
        openupgrade.logged_query(
            env.cr,
            """
            INSERT INTO ir_model_data
                (module, name, model, res_id, noupdate, create_date, write_date)
            SELECT 'mail', %s, 'discuss.channel.member', m.id, TRUE, NOW(), NOW()
            FROM discuss_channel_member m
            JOIN ir_model_data c ON c.model = 'discuss.channel'
                AND c.module = 'mail' AND c.name = %s AND c.res_id = m.channel_id
            JOIN ir_model_data p ON p.model = 'res.partner'
                AND p.module = 'base' AND p.name = 'partner_admin'
                AND p.res_id = m.partner_id
            WHERE NOT EXISTS (
                SELECT 1 FROM ir_model_data d
                WHERE d.module = 'mail' AND d.name = %s)
            """,
            (name, channel_xmlid, name),
        )


@openupgrade.migrate()
def migrate(env, version):
    _drop_legacy_access_xmlids(env)
    _tracking_values(env)
    _drop_not_null_on_removed_fields(env)
    _activity_type_suggested_next(env)
    _starred_to_bookmarked(env)
    _channel_member_xmlids(env)
