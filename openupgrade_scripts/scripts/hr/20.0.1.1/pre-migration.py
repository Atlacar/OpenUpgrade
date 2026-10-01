# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2.extras import Json

# hr.version#employee_type (selection, deleted in 20) -> hr.employee.type record.
# Value: (xmlid name in module hr, name used when there is no such record)
_EMPLOYEE_TYPE_MAPPING = {
    "employee": ("contract_type_employee", "Employee"),
    "student": ("contract_type_student", "Student"),
    "trainee": ("contract_type_intern", "Intern"),
    "worker": (None, "Worker"),
    "contractor": (None, "Contractor"),
    "freelance": (None, "Freelancer"),
}


def contract_type_to_employee_type(env):
    """hr.contract.type is replaced by hr.employee.type (same xmlids for the
    types that still exist in 20: employee, student, intern, interim,
    apprenticeship, thesis, seasonal). Keep the rows, rename model and table.
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, "hr_contract_type"):
        return
    openupgrade.rename_tables(cr, [("hr_contract_type", "hr_employee_type")])
    openupgrade.rename_models(cr, [("hr.contract.type", "hr.employee.type")])
    openupgrade.logged_query(
        cr,
        "UPDATE ir_model_data SET model = 'hr.employee.type' "
        "WHERE model = 'hr.contract.type'",
    )


def _get_or_create_employee_type(env, xmlid_name, label):
    cr = env.cr
    if xmlid_name:
        cr.execute(
            """
            SELECT res_id FROM ir_model_data
            WHERE module = 'hr' AND name = %s AND model = 'hr.employee.type'
            """,
            (xmlid_name,),
        )
        row = cr.fetchone()
        if row:
            return row[0]
    cr.execute(
        "SELECT id FROM hr_employee_type WHERE name->>'en_US' = %s ORDER BY id LIMIT 1",
        (label,),
    )
    row = cr.fetchone()
    if row:
        return row[0]
    cr.execute(
        """
        INSERT INTO hr_employee_type
            (name, code, sequence, create_uid, create_date, write_uid, write_date)
        VALUES (%s, %s, 10, 1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC')
        RETURNING id
        """,
        (Json({"en_US": label}), label),
    )
    return cr.fetchone()[0]


def employee_type_id(env):
    """hr.version#employee_type (selection) and hr.version#contract_type_id /
    hr.job#contract_type_id are replaced by hr.version#employee_type_id and
    hr.job#employee_type_id.
    """
    cr = env.cr
    openupgrade.add_columns(
        env,
        [
            ("hr.version", "employee_type_id", "many2one", None, "hr_version"),
            ("hr.job", "employee_type_id", "many2one", None, "hr_job"),
        ],
    )
    if openupgrade.column_exists(cr, "hr_version", "contract_type_id"):
        openupgrade.logged_query(
            cr,
            "UPDATE hr_version SET employee_type_id = contract_type_id "
            "WHERE contract_type_id IS NOT NULL",
        )
    if openupgrade.column_exists(cr, "hr_job", "contract_type_id"):
        openupgrade.logged_query(
            cr,
            "UPDATE hr_job SET employee_type_id = contract_type_id "
            "WHERE contract_type_id IS NOT NULL",
        )
    if openupgrade.column_exists(cr, "hr_version", "employee_type"):
        cr.execute(
            "SELECT DISTINCT employee_type FROM hr_version "
            "WHERE employee_type IS NOT NULL AND employee_type_id IS NULL"
        )
        for (key,) in cr.fetchall():
            xmlid_name, label = _EMPLOYEE_TYPE_MAPPING.get(
                key, (None, key.capitalize())
            )
            type_id = _get_or_create_employee_type(env, xmlid_name, label)
            openupgrade.logged_query(
                cr,
                "UPDATE hr_version SET employee_type_id = %s "
                "WHERE employee_type = %s AND employee_type_id IS NULL",
                (type_id, key),
            )


def employee_stored_fields(env):
    """hr.employee#additional_note and #contract_template_id were related to
    the current version, they are stored on hr.employee in 20.
    """
    cr = env.cr
    cr.execute(
        "ALTER TABLE hr_employee ADD COLUMN IF NOT EXISTS contract_template_id int4"
    )
    cr.execute("ALTER TABLE hr_employee ADD COLUMN IF NOT EXISTS additional_note text")
    openupgrade.logged_query(
        cr,
        """
        UPDATE hr_employee e
        SET contract_template_id = v.contract_template_id
        FROM hr_version v
        WHERE v.id = e.current_version_id AND v.contract_template_id IS NOT NULL
        """,
    )
    # hr.version#additional_note is deleted: move it to the employee
    if openupgrade.column_exists(cr, "hr_version", "additional_note"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE hr_employee e
            SET additional_note = concat_ws(
                chr(10), NULLIF(e.additional_note, ''), v.additional_note
            )
            FROM hr_version v
            WHERE v.id = e.current_version_id
                AND COALESCE(v.additional_note, '') != ''
            """,
        )


def version_required_fields(env):
    """hr.version#tz is stored and required (was related to the employee, i.e. to
    resource.resource#tz); hr.version#resource_calendar_id and hr.job#company_id
    are required.
    """
    cr = env.cr
    cr.execute("ALTER TABLE hr_version ADD COLUMN IF NOT EXISTS tz varchar")
    openupgrade.logged_query(
        cr,
        """
        UPDATE hr_version v
        SET tz = rr.tz
        FROM hr_employee e
        JOIN resource_resource rr ON rr.id = e.resource_id
        WHERE v.employee_id = e.id AND rr.tz IS NOT NULL AND v.tz IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE hr_version v
        SET resource_calendar_id = COALESCE(
            (SELECT e.resource_calendar_id FROM hr_employee e
             WHERE e.id = v.employee_id),
            (SELECT c.resource_calendar_id FROM res_company c
             WHERE c.id = v.company_id)
        )
        WHERE v.resource_calendar_id IS NULL
        """,
    )
    # contract templates (no employee) and fallback: calendar timezone, then UTC
    openupgrade.logged_query(
        cr,
        """
        UPDATE hr_version v
        SET tz = COALESCE(
            (SELECT rc.tz FROM resource_calendar rc
             WHERE rc.id = v.resource_calendar_id),
            'UTC'
        )
        WHERE v.tz IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE hr_job
        SET company_id = (SELECT id FROM res_company ORDER BY id LIMIT 1)
        WHERE company_id IS NULL
        """,
    )


def version_new_fields(env):
    """hr.version#fixed_term (new): a contract with an end date is fixed term,
    same rule as the onchange of 20. New check: wage >= 0.
    """
    openupgrade.add_columns(
        env, [("hr.version", "fixed_term", "boolean", False, "hr_version")]
    )
    openupgrade.logged_query(
        env.cr,
        "UPDATE hr_version SET fixed_term = TRUE WHERE contract_date_end IS NOT NULL",
    )
    openupgrade.logged_query(env.cr, "UPDATE hr_version SET wage = 0 WHERE wage < 0")


def departure_legacy_columns(env):
    """hr.version#departure_{reason_id,date,description} become related fields
    to the new model hr.employee.departure: keep the values to create the
    departure records in post-migration.
    """
    cr = env.cr
    spec = [
        (col, None, None)
        for col in ("departure_reason_id", "departure_date", "departure_description")
        if openupgrade.column_exists(cr, "hr_version", col)
    ]
    if spec:
        openupgrade.copy_columns(cr, {"hr_version": spec})


def job_recruiter(env):
    """hr.job#user_id (res.users) is replaced by hr.job#recruiter_id (employee)"""
    cr = env.cr
    openupgrade.add_columns(
        env, [("hr.job", "recruiter_id", "many2one", None, "hr_job")]
    )
    if openupgrade.column_exists(cr, "hr_job", "user_id"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE hr_job j
            SET recruiter_id = (
                SELECT e.id FROM hr_employee e
                WHERE e.user_id = j.user_id
                ORDER BY (e.company_id = j.company_id) DESC, e.id
                LIMIT 1
            )
            WHERE j.user_id IS NOT NULL
            """,
        )


def map_removed_selection_keys(env):
    cr = env.cr
    # hr.version#sex: key 'other' removed (0 rows in production)
    openupgrade.logged_query(cr, "UPDATE hr_version SET sex = NULL WHERE sex = 'other'")
    # mail.activity.plan.template#responsible_type: key 'coach' removed
    # (0 rows in production)
    openupgrade.logged_query(
        cr,
        "UPDATE mail_activity_plan_template SET responsible_type = 'manager' "
        "WHERE responsible_type = 'coach'",
    )


@openupgrade.migrate()
def migrate(env, version):
    contract_type_to_employee_type(env)
    employee_type_id(env)
    employee_stored_fields(env)
    version_required_fields(env)
    version_new_fields(env)
    departure_legacy_columns(env)
    job_recruiter(env)
    map_removed_selection_keys(env)
