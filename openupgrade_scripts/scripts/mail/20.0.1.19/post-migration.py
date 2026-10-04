# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

BATCH_SIZE = 2000
LEGACY_SCRAP_MESSAGE_TABLE = "openupgrade_legacy_20_0_stock_scrap_mail_message"

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


def _main_user_setting(env, column):
    env.cr.execute(
        f"""
        SELECT p.{column} FROM res_users u JOIN res_partner p ON p.id = u.partner_id
        WHERE u.active AND p.{column} IS NOT NULL
        GROUP BY p.{column} ORDER BY COUNT(*) DESC LIMIT 1
        """  # noqa: E8103
    )
    row = env.cr.fetchone()
    return row[0] if row else None


def _escape(text):
    """Same escaping as qweb t-out (markupsafe)."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&#39;")
        .replace('"', "&#34;")
    )


class OdooFormatter:
    """Formatting of tracking values with the Odoo 20 helpers themselves
    (mail.track.mixin._create_mail_tracking_values), in one language/timezone."""

    def __init__(self, env, lang, tz):
        from odoo.tools.misc import format_amount, formatLang

        self._format_amount = format_amount
        self._format_lang = formatLang
        self.env = env(context=dict(env.context, lang=lang, tz=tz or "UTC"))
        self.mixin = self.env["mail.track.mixin"]
        self._currencies = {}

    def yes_no(self, value):
        return self.env._("Yes") if value else self.env._("No")

    def number(self, value, integer):
        return self._format_lang(
            self.env, value or 0, rounding_unit="units" if integer else "decimals"
        )

    def amount(self, value, currency_id):
        if currency_id not in self._currencies:
            currency = self.env["res.currency"].browse(currency_id).exists()
            self._currencies[currency_id] = currency
        currency = self._currencies[currency_id]
        if not currency:
            return self.number(value, False)
        return self._format_amount(self.env, value or 0, currency)

    def datetime(self, value):
        return self.mixin._format_tracking_datetime(value)

    def date(self, value):
        return self.mixin._format_tracking_date(value.date())


def format_tracking_value(kind, vals, fmt, currency_id=None):
    """Display text of one side (old or new) of a tracking value, with the rules of
    mail.track.mixin._create_mail_tracking_values (Odoo 20).

    :param kind: field type (ir.model.fields.ttype or field_info['type'])
    :param vals: dict with the legacy columns ``integer``, ``float``, ``char``,
        ``text``, ``datetime``
    :param fmt: formatter (yes_no, number, amount, datetime, date)
    """
    if kind in ("char", "text"):
        return vals["char"] or vals["text"] or "None"
    if kind in ("selection", "many2one", "one2many", "many2many", "tags"):
        return vals["char"] or "None"
    if kind in ("integer", "float"):
        return fmt.number(vals[kind], kind == "integer")
    if kind == "monetary":
        if currency_id:
            return fmt.amount(vals["float"], currency_id)
        return fmt.number(vals["float"], False)
    if kind == "datetime":
        return fmt.datetime(vals["datetime"]) if vals["datetime"] else "None"
    if kind == "date":
        return fmt.date(vals["datetime"]) if vals["datetime"] else "None"
    if kind == "boolean":
        return fmt.yes_no(vals["integer"])
    return vals["char"] or vals["text"] or "None"


def render_tracking_html(items):
    """HTML appended to the body of a tracking message, same markup as the qweb
    template ``mail.mail_tracking_template`` of Odoo 20.

    :param items: list of ``(company_name, old_text, new_text, label)`` in the
        display order (descending mail.tracking.value id, as Odoo reverses the
        creation order)
    """
    lines = []
    for company_name, old_text, new_text, label in items:
        line = ""
        if company_name:
            line += "<em>%s: </em>" % _escape(company_name)
        if old_text:
            line += _escape(old_text)
        line += " → <b>%s</b> <i>(%s)</i>" % (_escape(new_text), _escape(label))
        lines.append(line)
    return "<div>%s</div>" % "<br/>".join(lines)


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
    lang = _main_user_setting(env, "lang") or "en_US"
    tz = _main_user_setting(env, "tz")
    fmt = OdooFormatter(env, lang, tz)
    if openupgrade.column_exists(cr, "mail_tracking_value", "currency_id"):
        currency_sql = "COALESCE(t.currency_id, (t.field_info->>'currency_id')::int)"
    else:
        currency_sql = "(t.field_info->>'currency_id')::int"
    cr.execute(
        f"""
        SELECT t.mail_message_id,
            COALESCE(f.ttype, t.field_info->>'type', 'char') AS kind,
            COALESCE(
                f.field_description->>%(lang)s,
                f.field_description->>'en_US',
                t.field_info->>'desc',
                t.field_info->>'name',
                'Unknown'
            ) AS label,
            {currency_sql},
            (t.field_info->>'company_id')::int,
            t.old_value_integer, t.old_value_float, t.old_value_char,
            t.old_value_text, t.old_value_datetime,
            t.new_value_integer, t.new_value_float, t.new_value_char,
            t.new_value_text, t.new_value_datetime
        FROM mail_tracking_value t
        JOIN mail_message m ON m.id = t.mail_message_id
        LEFT JOIN ir_model_fields f ON f.id = t.field_id
        WHERE m.message_type != 'tracking'
        ORDER BY t.mail_message_id, t.id DESC
        """,  # noqa: E8103
        {"lang": lang},
    )
    company_names = {}
    items_by_message = {}
    for row in cr.fetchall():
        message_id, kind, label, currency_id, company_id = row[:5]
        old = dict(zip(("integer", "float", "char", "text", "datetime"), row[5:10]))
        new = dict(zip(("integer", "float", "char", "text", "datetime"), row[10:15]))
        if company_id and company_id not in company_names:
            cr.execute("SELECT name FROM res_company WHERE id = %s", (company_id,))
            found = cr.fetchone()
            company_names[company_id] = found[0] if found else None
        items_by_message.setdefault(message_id, []).append(
            (
                company_names.get(company_id),
                format_tracking_value(kind, old, fmt, currency_id),
                format_tracking_value(kind, new, fmt, currency_id),
                label,
            )
        )
    message_ids = list(items_by_message)
    for start in range(0, len(message_ids), BATCH_SIZE):
        chunk = message_ids[start : start + BATCH_SIZE]
        htmls = [render_tracking_html(items_by_message[mid]) for mid in chunk]
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
        "tracking values rendered in the body of %s messages (lang %s, tz %s)",
        len(message_ids),
        lang,
        tz,
    )


def _keep_scrap_messages(env):
    """stock.scrap is merged into stock.move (not a mail.thread): when the
    obsolete model is removed at the end of the update, ir.model's
    ``_unlink_related_mail_data`` runs ``DELETE FROM mail_message WHERE model =
    'stock.scrap'`` and the tracking rows of those messages are removed by the
    ON DELETE CASCADE foreign key. This is the only obsolete model of aquila with
    messages (26 messages, 13 with tracking rows). Their history has no target in
    20, so keep a readable copy (body already rendered above) and say it."""
    cr = env.cr
    if not openupgrade.table_exists(cr, "stock_scrap"):
        return
    if not openupgrade.table_exists(cr, LEGACY_SCRAP_MESSAGE_TABLE):
        openupgrade.logged_query(
            cr,
            f"""
            CREATE TABLE {LEGACY_SCRAP_MESSAGE_TABLE} AS
            SELECT m.*, s.name AS legacy_scrap_name
            FROM mail_message m
            LEFT JOIN stock_scrap s ON s.id = m.res_id
            WHERE m.model = 'stock.scrap'
            """,
        )
    cr.execute(
        f"""
        SELECT COUNT(*),
            COUNT(*) FILTER (WHERE id IN (
                SELECT mail_message_id FROM mail_tracking_value))
        FROM {LEGACY_SCRAP_MESSAGE_TABLE}
        """  # noqa: E8103
    )
    messages, tracked = cr.fetchone()
    if messages:
        _logger.warning(
            "stock.scrap is not a mail.thread in 20: %s messages (%s with tracking "
            "rows) of scrap records are deleted with the obsolete model; readable "
            "copy kept in %s",
            messages,
            tracked,
            LEGACY_SCRAP_MESSAGE_TABLE,
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
    _keep_scrap_messages(env)
    _channel_owner(env)
    _activity_type_icons(env)
