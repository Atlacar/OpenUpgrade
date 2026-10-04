# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_deleted_xmlids = [
    # hr.employee.type records of the former hr.contract.type that are not part
    # of the 20 data (deleted only if not referenced)
    "hr.contract_type_permanent",
    "hr.contract_type_temporary",
    "hr.contract_type_full_time",
    "hr.contract_type_part_time",
    "hr.contract_type_statutory",
    # payroll structure types that are demo data in 20 (deleted only if unused)
    "hr.structure_type_worker",
    "hr.structure_type_employee_cp200_pfi",
    # ir.rule that have no ir.access equivalent in 20 (no-op if the conversion of
    # ir.rule to ir.access did not keep them)
    "hr.hr_employee_public_comp_rule",
    "hr.ir_rule_hr_contract_manager",
]


def create_departures(env):
    """hr.version#departure_{reason_id,date,description} were stored fields on
    the version, they now live in the new model hr.employee.departure, linked by
    hr.version#departure_id. One departure per employee, taken from its latest
    version carrying a departure reason; every version of the employee with the
    same reason and date is linked to it.
    """
    cr = env.cr
    reason = openupgrade.get_legacy_name("departure_reason_id")
    date = openupgrade.get_legacy_name("departure_date")
    description = openupgrade.get_legacy_name("departure_description")
    if not openupgrade.column_exists(cr, "hr_version", reason):
        return
    cr.execute(
        f"""
        SELECT DISTINCT ON (employee_id)
            employee_id, {reason}, {date}, {description}, contract_date_end
        FROM hr_version
        WHERE employee_id IS NOT NULL AND {reason} IS NOT NULL
        ORDER BY employee_id, date_version DESC, id DESC
        """
    )
    for employee_id, reason_id, date_, description_, contract_date_end in cr.fetchall():
        cr.execute(
            """
            INSERT INTO hr_employee_departure (
                employee_id, departure_reason_id, departure_description,
                dismissal_date, departure_date, action_date, apply_date,
                last_contract_date_end,
                create_uid, create_date, write_uid, write_date
            )
            SELECT
                %(employee)s, %(reason)s, %(description)s,
                d, d, d + 1,
                CASE WHEN d + 1 <= CURRENT_DATE THEN d + 1 END,
                %(contract_end)s,
                1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC'
            FROM (SELECT COALESCE(%(date)s::date, CURRENT_DATE) AS d) dates
            RETURNING id
            """,
            {
                "employee": employee_id,
                "reason": reason_id,
                "description": description_,
                "date": date_,
                "contract_end": contract_date_end,
            },
        )
        departure_id = cr.fetchone()[0]
        openupgrade.logged_query(
            cr,
            f"""
            UPDATE hr_version
            SET departure_id = %s
            WHERE employee_id = %s AND {reason} = %s
                AND {date} IS NOT DISTINCT FROM %s
            """,
            (departure_id, employee_id, reason_id, date_),
        )


def _deactivate_overridden_accesses(env):
    """hr/security/hr_security.xml (noupdate) deactivates the base ir.access
    records `res_partner_bank_rule_user(_1)` and replaces them by the hr ones that
    restrict the employee bank accounts. A noupdate file is skipped on an update
    while base has just created these records (active), so they would stay active
    and give every internal user the unrestricted read/write of the base rule on top
    of the hr restriction. Replicate the install-time effect."""
    for xmlid in (
        "base.res_partner_bank_rule_user",
        "base.res_partner_bank_rule_user_1",
    ):
        access = env.ref(xmlid, raise_if_not_found=False)
        if access and access.active:
            access.with_context(tracking_disable=True).active = False


@openupgrade.migrate()
def migrate(env, version):
    create_departures(env)
    openupgrade.load_data(env, "hr", "20.0.1.1/noupdate_changes.xml")
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
    _deactivate_overridden_accesses(env)
