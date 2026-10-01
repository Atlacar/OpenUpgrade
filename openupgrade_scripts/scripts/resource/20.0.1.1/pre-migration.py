# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _drop_legacy_access_xmlids(env):
    """ir.model.access / ir.rule -> ir.access with identical xmlids (see
    mail/20.0.1.19/pre-migration.py). Defensive: no-op if base already did it."""
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'resource' AND model IN ('ir.model.access', 'ir.rule')
        """,
    )


def _drop_not_null_on_removed_fields(env):
    """Removed required fields keep their NOT NULL constraint until the ORM drops
    the column at the end of the update, which breaks the inserts done while the
    module data is loaded (e.g. default attendances)."""
    for table, column in (
        ("resource_calendar", "tz"),
        ("resource_calendar", "schedule_type"),
        ("resource_calendar_attendance", "name"),
    ):
        if openupgrade.column_exists(env.cr, table, column):
            openupgrade.logged_query(
                env.cr,
                'ALTER TABLE "%s" ALTER COLUMN "%s" DROP NOT NULL'  # noqa: E8103
                % (table, column),
            )


def _calendar_type(env):
    """schedule_type (flexible/fully_fixed) + flexible_hours -> calendar_type
    (undefined/fixed). Variable calendars (new) replace the two weeks calendars
    (aquila: none)."""
    cr = env.cr
    cr.execute(
        "ALTER TABLE resource_calendar ADD COLUMN IF NOT EXISTS calendar_type varchar"
    )
    conditions = []
    if openupgrade.column_exists(cr, "resource_calendar", "schedule_type"):
        conditions.append("schedule_type = 'flexible'")
    if openupgrade.column_exists(cr, "resource_calendar", "flexible_hours"):
        conditions.append("flexible_hours IS TRUE")
    flexible = " OR ".join(conditions) or "FALSE"
    openupgrade.logged_query(
        cr,
        """
        UPDATE resource_calendar
        SET calendar_type = CASE WHEN %s THEN 'undefined' ELSE 'fixed' END
        """  # noqa: E8103
        % flexible,
    )
    if openupgrade.column_exists(cr, "resource_calendar", "two_weeks_calendar"):
        cr.execute("SELECT id FROM resource_calendar WHERE two_weeks_calendar IS TRUE")
        if cr.rowcount:
            _logger.warning(
                "resource.calendar %s use the removed 'two weeks calendar' mode: "
                "convert them by hand to variable calendars",
                [row[0] for row in cr.fetchall()],
            )
    if openupgrade.column_exists(cr, "resource_calendar", "duration_based"):
        cr.execute("SELECT id FROM resource_calendar WHERE duration_based IS TRUE")
        if cr.rowcount:
            _logger.warning(
                "resource.calendar %s were duration based: the flag is now per "
                "attendance (hour_from = hour_to = 0)",
                [row[0] for row in cr.fetchall()],
            )


def _reference_calendar(env):
    """reference_calendar_id (new, defaults to the calendar of the company):
    set it now to avoid the ORM default computed for the company of the
    superuser."""
    cr = env.cr
    cr.execute(
        "ALTER TABLE resource_calendar "
        "ADD COLUMN IF NOT EXISTS reference_calendar_id integer"
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE resource_calendar c
        SET reference_calendar_id = COALESCE(
            (SELECT rc.resource_calendar_id FROM res_company rc
             WHERE rc.id = c.company_id),
            (SELECT rc.resource_calendar_id FROM res_company rc
             WHERE rc.resource_calendar_id IS NOT NULL ORDER BY rc.id LIMIT 1)
        )
        """,
    )


def _company_tz(env):
    """resource.calendar.tz is removed, res.company.tz (new) takes over: seed it
    with the timezone of the default calendar of the company, else the ORM would
    compute 'UTC' (several timezones in the country, no user during upgrade)."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "resource_calendar", "tz"):
        return
    cr.execute("ALTER TABLE res_company ADD COLUMN IF NOT EXISTS tz varchar")
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_company rc
        SET tz = COALESCE(
            (SELECT c.tz FROM resource_calendar c
             WHERE c.id = rc.resource_calendar_id),
            (SELECT c.tz FROM resource_calendar c
             WHERE c.company_id = rc.id ORDER BY c.id LIMIT 1)
        )
        WHERE rc.tz IS NULL
        """,
    )


def _attendances(env):
    cr = env.cr
    # lunch breaks were 0 hour attendance lines: they violate the new
    # CHECK(duration_hours > 0) and are not working time. Odoo 20 default
    # calendars simply have a gap (8-12, 13-17).
    if openupgrade.column_exists(cr, "resource_calendar_attendance", "day_period"):
        openupgrade.logged_query(
            cr,
            "DELETE FROM resource_calendar_attendance WHERE day_period = 'lunch'",
        )
    # section lines of two weeks calendars
    if openupgrade.column_exists(cr, "resource_calendar_attendance", "display_type"):
        openupgrade.logged_query(
            cr,
            "DELETE FROM resource_calendar_attendance "
            "WHERE display_type = 'line_section'",
        )
    if openupgrade.column_exists(cr, "resource_calendar_attendance", "week_type"):
        cr.execute(
            "SELECT DISTINCT calendar_id FROM resource_calendar_attendance "
            "WHERE week_type IS NOT NULL"
        )
        if cr.rowcount:
            _logger.warning(
                "resource.calendar %s have week_type attendances (two weeks "
                "calendar, removed in Odoo 20): not converted",
                [row[0] for row in cr.fetchall()],
            )


def _leaves_count_as(env):
    """time_type: leave -> absence, other -> working_time"""
    cr = env.cr
    if not openupgrade.column_exists(cr, "resource_calendar_leaves", "time_type"):
        return
    cr.execute(
        "ALTER TABLE resource_calendar_leaves "
        "ADD COLUMN IF NOT EXISTS count_as varchar"
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE resource_calendar_leaves
        SET count_as = CASE WHEN time_type = 'other' THEN 'working_time'
            ELSE 'absence' END
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _drop_legacy_access_xmlids(env)
    # resource.resource.color was defined in resource_mail. resource_mail is
    # loaded after resource, so the xmlid has to be moved from here
    openupgrade.update_module_moved_fields(
        env.cr, "resource.resource", ["color"], "resource_mail", "resource"
    )
    _drop_not_null_on_removed_fields(env)
    _calendar_type(env)
    _reference_calendar(env)
    _company_tz(env)
    _attendances(env)
    _leaves_count_as(env)
