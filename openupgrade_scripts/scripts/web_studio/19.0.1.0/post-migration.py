# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _mail_activity_studio_approval_request_id(env):
    """New inverse of studio.approval.request#mail_activity_id"""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE mail_activity activity
        SET studio_approval_request_id = request.id
        FROM studio_approval_request request
        WHERE request.mail_activity_id = activity.id
            AND activity.studio_approval_request_id IS NULL
        """,
    )


def _mail_activity_data_approve(env):
    """Approval activities are To-Do activities linked to the approval request in
    19.0: the 'Grant Approval' activity type is removed."""
    activity_type = env.ref(
        "web_studio.mail_activity_data_approve", raise_if_not_found=False
    )
    todo = env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
    if activity_type and todo:
        openupgrade.logged_query(
            env.cr,
            "UPDATE mail_activity SET activity_type_id = %s "
            "WHERE activity_type_id = %s",
            (todo.id, activity_type.id),
        )
    openupgrade.delete_records_safely_by_xml_id(
        env, ["web_studio.mail_activity_data_approve"]
    )


@openupgrade.migrate()
def migrate(env, version):
    _mail_activity_studio_approval_request_id(env)
    _mail_activity_data_approve(env)
