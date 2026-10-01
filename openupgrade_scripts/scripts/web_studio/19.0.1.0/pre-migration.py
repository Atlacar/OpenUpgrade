# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # selection key 'grant_approval' of mail.activity.type#category is removed
    # (it was declared with ondelete 'set default')
    openupgrade.logged_query(
        env.cr,
        "UPDATE mail_activity_type SET category = 'default' "
        "WHERE category = 'grant_approval'",
    )
