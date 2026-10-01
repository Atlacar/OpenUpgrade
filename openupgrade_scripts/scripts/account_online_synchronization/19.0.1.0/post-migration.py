# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _bank_sync_activity_update_consent(env):
    """The activity type 'Bank Synchronization: Update consent' is removed: keep the
    pending activities as generic to-dos and remove the type."""
    activity_type = env.ref(
        "account_online_synchronization.bank_sync_activity_update_consent",
        raise_if_not_found=False,
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
        env, ["account_online_synchronization.bank_sync_activity_update_consent"]
    )


@openupgrade.migrate()
def migrate(env, version):
    _bank_sync_activity_update_consent(env)
