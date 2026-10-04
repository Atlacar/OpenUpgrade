# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.addons.openupgrade_framework import template_tools


def generate_primary_calendars(env):
    """20.0 introduces calendar.calendar / calendar.user: every internal user
    (and every organizer of an event) owns a primary calendar. The module only
    creates them in its post_init_hook, i.e. on installation.
    """
    env.cr.execute(
        """
        SELECT id FROM res_users u
        WHERE (
            NOT COALESCE(u.share, FALSE)
            OR EXISTS (SELECT 1 FROM calendar_event e WHERE e.user_id = u.id)
        ) AND NOT EXISTS (
            SELECT 1 FROM calendar_user cu
            WHERE cu.user_id = u.id AND cu.is_primary
        )
        """
    )
    user_ids = [row[0] for row in env.cr.fetchall()]
    if user_ids:
        env["res.users"].with_context(active_test=False).browse(
            user_ids
        ).sudo()._generate_primary_calendar()
        env["calendar.calendar"].flush_model()
        env["calendar.user"].flush_model()


def calendar_default_privacy(env):
    """res.users.settings#calendar_default_privacy moved to the primary
    calendar of the user (calendar.calendar#calendar_default_privacy)
    """
    if not openupgrade.column_exists(
        env.cr, "res_users_settings", "calendar_default_privacy"
    ):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE calendar_calendar cal
        SET calendar_default_privacy = settings.calendar_default_privacy
        FROM calendar_user cu
        JOIN res_users_settings settings ON settings.user_id = cu.user_id
        WHERE cu.calendar_id = cal.id AND cu.is_primary
            AND settings.calendar_default_privacy IN
                ('public', 'private', 'confidential')
        """,
    )


def calendar_event_calendar(env):
    """calendar.event#calendar_id is the primary calendar of the organizer"""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE calendar_event event
        SET calendar_id = cu.calendar_id
        FROM calendar_user cu
        WHERE cu.user_id = event.user_id AND cu.is_primary
            AND cu.access_role = 'owner' AND event.calendar_id IS NULL
        """,
    )
    # res.users#primary_calendar_id is stored: make sure it is up to date
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_users u
        SET primary_calendar_id = cu.calendar_id
        FROM calendar_user cu
        WHERE cu.user_id = u.id AND cu.is_primary AND cu.access_role = 'owner'
            AND u.primary_calendar_id IS DISTINCT FROM cu.calendar_id
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    template_tools.load_data_keep_customized(env, "calendar", "20.0.1.1/noupdate_changes.xml")
    generate_primary_calendars(env)
    calendar_default_privacy(env)
    calendar_event_calendar(env)
