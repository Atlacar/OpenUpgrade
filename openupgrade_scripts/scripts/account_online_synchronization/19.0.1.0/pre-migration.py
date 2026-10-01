# Copyright 2026 Aquila Motopartes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_added_fields = [
    (
        "renewal_contact_email",
        "account.online.link",
        "account_online_link",
        "char",
        False,
        "account_online_synchronization",
    ),
]


def _account_online_link_renewal_contact_email(env):
    """account.journal#renewal_contact_email is now a related field to the new
    stored account.online.link#renewal_contact_email: fill the latter with the
    (comma separated) addresses of the journals of the connection, before the
    journal column becomes obsolete. Pre-create the column so the default (email
    of the user running the migration) is not applied."""
    openupgrade.add_fields(env, _added_fields)
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_online_link link
        SET renewal_contact_email = journal_emails.emails
        FROM (
            SELECT account_online_link_id,
                string_agg(DISTINCT renewal_contact_email, ',') AS emails
            FROM account_journal
            WHERE account_online_link_id IS NOT NULL
                AND renewal_contact_email IS NOT NULL
                AND renewal_contact_email != ''
            GROUP BY account_online_link_id
        ) journal_emails
        WHERE journal_emails.account_online_link_id = link.id
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _account_online_link_renewal_contact_email(env)
