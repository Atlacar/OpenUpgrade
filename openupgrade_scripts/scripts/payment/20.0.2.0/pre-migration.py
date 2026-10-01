# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


def payment_provider(env):
    """payment.provider#state (disabled / enabled / test) is replaced by:
    - is_live: True for 'enabled' (production mode), False for 'test' / 'disabled';
    - is_published: kept, forced to False for 'disabled';
    - active: a 'disabled' provider whose module is installed (code != 'none') is
      archived. The providers with code 'none' are the catalog entries of the
      modules that are not installed: they stay active as the 20.0 data creates
      them.
    prod: Wire Transfer / Pay on Site enabled, Cash on Delivery disabled,
    21 catalog providers disabled with code 'none'."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "payment_provider", "is_live"):
        cr.execute("ALTER TABLE payment_provider ADD COLUMN is_live boolean")
    if not openupgrade.column_exists(cr, "payment_provider", "active"):
        cr.execute("ALTER TABLE payment_provider ADD COLUMN active boolean")
    openupgrade.logged_query(
        cr,
        """
        UPDATE payment_provider
        SET is_live = (state = 'enabled'),
            is_published = CASE WHEN state = 'disabled' THEN FALSE
                ELSE is_published END,
            active = NOT (state = 'disabled' AND code != 'none')
        """,
    )


def payment_method(env):
    """payment.method used to be a catalog shared by providers (m2m
    payment_method_payment_provider_rel); in 20.0 every method belongs to one
    provider (provider_id, required) and is created by the data of the provider
    module (new xmlids). The 229 shared catalog xmlids of 'payment' are dropped.

    - the methods in use (transactions / tokens) or linked to a provider of an
      installed module (code != 'none') are kept and get that provider
      (prod: wire_transfer -> Wire Transfer, pay_on_site -> Pay on Site,
      cash_on_delivery -> Cash on Delivery, the only installed providers);
    - the other methods are catalog entries of providers whose module is not
      installed (prod: 224 methods, all inactive, no transaction, no token):
      removed, they are recreated per provider when its module is installed."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "payment_method", "provider_id"):
        cr.execute("ALTER TABLE payment_method ADD COLUMN provider_id integer")
    for table in ("payment_transaction", "payment_token"):
        openupgrade.logged_query(
            cr,
            f"""
            UPDATE payment_method pm
            SET provider_id = ref.provider_id
            FROM (
                SELECT DISTINCT ON (payment_method_id)
                    payment_method_id, provider_id
                FROM {table}
                WHERE payment_method_id IS NOT NULL AND provider_id IS NOT NULL
                ORDER BY payment_method_id, id
            ) ref
            WHERE pm.id = ref.payment_method_id AND pm.provider_id IS NULL
            """,
        )
    openupgrade.logged_query(
        cr,
        """
        UPDATE payment_method pm
        SET provider_id = rel.provider_id
        FROM (
            SELECT DISTINCT ON (r.payment_method_id)
                r.payment_method_id, r.payment_provider_id AS provider_id
            FROM payment_method_payment_provider_rel r
            JOIN payment_provider p ON p.id = r.payment_provider_id
            WHERE p.code != 'none'
            ORDER BY r.payment_method_id, p.id
        ) rel
        WHERE pm.id = rel.payment_method_id AND pm.provider_id IS NULL
        """,
    )
    cr.execute("SELECT id FROM payment_method WHERE provider_id IS NULL")
    removed = tuple(row[0] for row in cr.fetchall())
    if removed:
        cr.execute(
            "DELETE FROM ir_model_data WHERE model = 'payment.method' "
            "AND res_id IN %s",
            (removed,),
        )
        cr.execute(
            "DELETE FROM payment_method_payment_provider_rel "
            "WHERE payment_method_id IN %s",
            (removed,),
        )
        cr.execute("DELETE FROM payment_method WHERE id IN %s", (removed,))
    openupgrade.logger.info(
        "payment.method: %s catalog methods without installed provider removed",
        len(removed),
    )


@openupgrade.migrate()
def migrate(env, version):
    payment_provider(env)
    payment_method(env)
