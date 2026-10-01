# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from html import escape

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

BATCH_SIZE = 2000

# fa-* (font awesome) -> Material Symbols names: Odoo 20 renders
# mail.activity.type.icon with data-icon (Material Symbols)
ACTIVITY_ICON_MAP = {
    "fa-envelope": "mail",
    "fa-phone": "phone",
    "fa-users": "group",
    "fa-check": "check",
    "fa-upload": "upload",
    "fa-warning": "warning",
    "fa-tasks": "checklist",
    "fa-calendar": "calendar_today",
    "fa-file-text-o": "description",
    "fa-clock-o": "schedule",
}
ACTIVITY_ICON_DEFAULT = "check"


def _main_lang(env):
    env.cr.execute(
        """
        SELECT p.lang FROM res_users u JOIN res_partner p ON p.id = u.partner_id
        WHERE u.active AND p.lang IS NOT NULL
        GROUP BY p.lang ORDER BY COUNT(*) DESC LIMIT 1
        """
    )
    row = env.cr.fetchone()
    return row[0] if row else "en_US"


def _currencies(env):
    cr = env.cr
    columns = ["id", "symbol"]
    for column in ("position", "decimal_places"):
        if openupgrade.column_exists(cr, "res_currency", column):
            columns.append(column)
    cr.execute("SELECT %s FROM res_currency" % ", ".join(columns))  # noqa: E8103
    return {row[0]: dict(zip(columns, row)) for row in cr.fetchall()}


def _format_value(kind, vals, currencies, currency_id, env_lang):
    """Same display rules as mail.track.mixin._create_mail_tracking_values (the
    'old_value'/'new_value' of Odoo 20), computed from the legacy columns of
    mail_tracking_value (``vals``: integer, float, char, text, datetime)."""
    if kind in ("char", "text", "selection", "many2one", "many2many", "one2many", "tags"):
        return vals["char"] or vals["text"] or "None"
    if kind == "integer":
        return "{:,}".format(vals["integer"] or 0)
    if kind == "float":
        return "{:,.2f}".format(vals["float"] or 0.0)
    if kind == "monetary":
        amount = vals["float"] or 0.0
        currency = currencies.get(currency_id)
        if not currency:
            return "{:,.2f}".format(amount)
        text = "{:,.{}f}".format(amount, currency.get("decimal_places") or 2)
        if currency.get("position") == "after":
            return "%s %s" % (text, currency["symbol"] or "")
        return "%s %s" % (currency["symbol"] or "", text)
    if kind == "datetime":
        value = vals["datetime"]
        return value.strftime("%Y-%m-%d %H:%M:%S (UTC)") if value else "None"
    if kind == "date":
        value = vals["datetime"]
        return value.strftime("%Y-%m-%d") if value else "None"
    if kind == "boolean":
        return env_lang._("Yes") if vals["integer"] else env_lang._("No")
    return vals["char"] or vals["text"] or "None"


def _tracking_values_to_body(env):
    """Odoo 20 mail renders the tracking of a message from mail_message.body (see
    mail.thread._message_compute_body_with_trackings and the qweb template
    mail.mail_tracking_template) and flags those messages with the new
    message_type 'tracking'. Odoo 19 kept an empty body and rendered the
    mail_tracking_value rows on the fly: without this conversion the whole
    chatter history of changes (31.6k messages in aquila) would appear blank,
    whether or not mail_tracking is installed (the module only keeps the
    technical table and its admin menu).
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, "mail_tracking_value"):
        return
    lang = _main_lang(env)
    env_lang = env(context=dict(env.context, lang=lang))
    currencies = _currencies(env)
    cr.execute(
        """
        SELECT t.mail_message_id, t.id,
            COALESCE(f.ttype, t.field_info->>'type', 'char') AS kind,
            COALESCE(
                f.field_description->>%(lang)s,
                f.field_description->>'en_US',
                t.field_info->>'desc',
                'Unknown'
            ) AS label,
            t.currency_id,
            t.old_value_integer, t.old_value_float, t.old_value_char,
            t.old_value_text, t.old_value_datetime,
            t.new_value_integer, t.new_value_float, t.new_value_char,
            t.new_value_text, t.new_value_datetime
        FROM mail_tracking_value t
        JOIN mail_message m ON m.id = t.mail_message_id
        LEFT JOIN ir_model_fields f ON f.id = t.field_id
        WHERE m.message_type != 'tracking'
        ORDER BY t.mail_message_id, t.id
        """,
        {"lang": lang},
    )
    html_by_message = {}
    for row in cr.fetchall():
        message_id, _tid, kind, label, currency_id = row[:5]
        old = dict(zip(("integer", "float", "char", "text", "datetime"), row[5:10]))
        new = dict(zip(("integer", "float", "char", "text", "datetime"), row[10:15]))
        old_text = _format_value(kind, old, currencies, currency_id, env_lang)
        new_text = _format_value(kind, new, currencies, currency_id, env_lang)
        html_by_message.setdefault(message_id, []).append(
            "%s → <b>%s</b> <i>(%s)</i>"
            % (escape(old_text), escape(new_text), escape(label))
        )
    message_ids = list(html_by_message)
    for start in range(0, len(message_ids), BATCH_SIZE):
        chunk = message_ids[start : start + BATCH_SIZE]
        htmls = ["<div>%s</div>" % "<br/>".join(html_by_message[mid]) for mid in chunk]
        cr.execute(
            """
            UPDATE mail_message m
            SET body = COALESCE(m.body, '') || v.html, message_type = 'tracking'
            FROM (
                SELECT UNNEST(%s::integer[]) AS id, UNNEST(%s::text[]) AS html
            ) v
            WHERE m.id = v.id
            """,
            (chunk, htmls),
        )
    _logger.info(
        "tracking values rendered in the body of %s messages", len(message_ids)
    )


def _channel_owner(env):
    """discuss.channel.member.channel_role is new: the creator of a channel/group
    is its owner (as Odoo 20 does at creation)."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE discuss_channel_member m
        SET channel_role = 'owner'
        FROM discuss_channel c
        JOIN res_users u ON u.id = c.create_uid
        WHERE m.channel_id = c.id AND m.partner_id = u.partner_id
            AND c.channel_type IN ('channel', 'group')
            AND m.channel_role IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM discuss_channel_member o
                WHERE o.channel_id = c.id AND o.channel_role = 'owner'
            )
        """,
    )


def _activity_type_icons(env):
    for old, new in ACTIVITY_ICON_MAP.items():
        env.cr.execute(
            "UPDATE mail_activity_type SET icon = %s WHERE icon = %s", (new, old)
        )
    env.cr.execute(
        "UPDATE mail_activity_type SET icon = %s WHERE icon LIKE 'fa-%%'",
        (ACTIVITY_ICON_DEFAULT,),
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "mail", "20.0.1.19/noupdate_changes.xml")
    _tracking_values_to_body(env)
    _channel_owner(env)
    _activity_type_icons(env)
