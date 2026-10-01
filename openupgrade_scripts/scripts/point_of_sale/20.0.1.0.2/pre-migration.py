# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


# pos_stock is a new auto_install module (point_of_sale + stock_account) that
# takes over the stock integration of point_of_sale. It has to be installed
# (force-install list of the orchestrator), otherwise the data of these fields
# is no longer reachable through the ORM.
_moved_to_pos_stock = {
    "pos.config": [
        "picking_policy",
        "picking_type_id",
        "route_id",
        "ship_later",
        "warehouse_id",
    ],
    "pos.order": [
        "failed_pickings",
        "picking_count",
        "picking_ids",
        "picking_type_id",
        "shipping_date",
        "stock_reference_ids",
    ],
    "pos.order.line": ["pack_lot_ids"],
    "pos.session": [
        "failed_pickings",
        "picking_count",
        "picking_ids",
        "update_stock_at_closing",
    ],
    "res.company": ["point_of_sale_update_stock_quantities"],
    "stock.picking": ["pos_order_id", "pos_session_id"],
    "stock.reference": ["pos_order_ids"],
    "stock.warehouse": ["pos_type_id"],
}

_renamed_fields = [
    # semantic is wider in 20 (terminals and qr codes), values are kept
    (
        "pos.config",
        "pos_config",
        "auto_validate_terminal_payment",
        "auto_validate_electronic_payment",
    ),
    ("pos.config", "pos_config", "is_header_or_footer", "use_header_or_footer"),
    (
        "pos.config",
        "pos_config",
        "is_closing_entry_by_product",
        "use_closing_entry_by_product",
    ),
    ("pos.config", "pos_config", "is_order_printer", "use_order_printer"),
]


def move_modules(env):
    cr = env.cr
    # model + all its fields moved to pos_stock
    openupgrade.update_module_moved_models(
        cr, "pos.pack.operation.lot", "point_of_sale", "pos_stock"
    )
    # fields of models that stay in point_of_sale (or in other modules)
    for model, fields_list in _moved_to_pos_stock.items():
        openupgrade.update_module_moved_fields(
            cr, model, fields_list, "point_of_sale", "pos_stock"
        )
    # pos.printer#company_id is now defined by pos_iot (not installed in aquila)
    openupgrade.update_module_moved_fields(
        cr, "pos.printer", ["company_id"], "point_of_sale", "pos_iot"
    )
    # preparation models: pos_enterprise -> point_of_sale. point_of_sale loads
    # first, so the move has to be done here and not in pos_enterprise
    for model in ("pos.prep.order", "pos.prep.line"):
        openupgrade.update_module_moved_models(
            cr, model, "pos_enterprise", "point_of_sale"
        )


def pos_config_journals(env):
    """
    v19 pos.config#journal_id (type general or sale, POSS journal) booked the session
    closing entries and pos.config#invoice_journal_id (type sale) the invoices.
    v20 pos.config#journal_id is the invoice journal (type sale) and the new required
    pos.config#closing_journal_id books the session closing entries (out_invoice /
    out_refund, so it must be of type sale).
    closing_journal_id is pre-filled with the invoice journal so that the required
    column never holds NULL while the modules load; the post script replaces it with
    the dedicated "Point of Sale Closing" journal.
    """
    cr = env.cr
    openupgrade.logged_query(
        cr,
        "ALTER TABLE pos_config ADD COLUMN IF NOT EXISTS closing_journal_id integer",
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_config pc
        SET closing_journal_id = COALESCE(
            (SELECT j.id FROM account_journal j
             WHERE j.id = pc.invoice_journal_id AND j.type = 'sale'),
            (SELECT j.id FROM account_journal j
             WHERE j.id = pc.journal_id AND j.type = 'sale'),
            (SELECT j.id FROM account_journal j
             WHERE j.company_id = pc.company_id AND j.type = 'sale'
             ORDER BY j.sequence, j.id LIMIT 1)
        )
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_config pc
        SET journal_id = j.id
        FROM account_journal j
        WHERE j.id = pc.invoice_journal_id AND j.type = 'sale'
        """,
    )
    # v20 point_of_sale searches/creates its POSS journal with type 'sale'
    # (account.journal#_ensure_pos_journal). The v19 POSS journal is of type
    # 'general' and holds the v19 closing entries: free the code, otherwise creating
    # a new POS configuration fails on the unique (code, company) constraint.
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_journal j
        SET code = 'POSL'
        WHERE j.code = 'POSS' AND j.type != 'sale'
        AND NOT EXISTS (
            SELECT 1 FROM account_journal j2
            WHERE j2.company_id = j.company_id AND j2.code = 'POSL'
        )
        """,
    )


def pos_payment_method_type(env):
    """
    pos.payment.method#type was computed from the journal (cash / bank, otherwise
    customer account) and is now a stored required field.
    pos.payment.method#payment_method_type 'qr_code' became 'bank_qr_code'.
    pos.payment.method#use_payment_terminal became payment_provider.
    pos.payment.method#image is now computed, its stored value is custom_image.
    """
    cr = env.cr
    openupgrade.logged_query(
        cr, "ALTER TABLE pos_payment_method ADD COLUMN IF NOT EXISTS type varchar"
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_payment_method pm
        SET type = CASE
            WHEN j.type IN ('cash', 'bank') THEN j.type
            ELSE 'pay_later'
        END
        FROM (SELECT pm2.id, aj.type
              FROM pos_payment_method pm2
              LEFT JOIN account_journal aj ON aj.id = pm2.journal_id) j
        WHERE j.id = pm.id
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_payment_method
        SET payment_method_type = 'bank_qr_code'
        WHERE payment_method_type = 'qr_code'
        """,
    )
    if openupgrade.column_exists(cr, "pos_payment_method", "use_payment_terminal"):
        openupgrade.logged_query(
            cr,
            "ALTER TABLE pos_payment_method "
            "ADD COLUMN IF NOT EXISTS payment_provider varchar",
        )
        openupgrade.logged_query(
            cr,
            """
            UPDATE pos_payment_method
            SET payment_provider = use_payment_terminal,
                payment_method_type = 'terminal'
            WHERE use_payment_terminal IS NOT NULL
            """,
        )
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_attachment
        SET res_field = 'custom_image'
        WHERE res_model = 'pos.payment.method' AND res_field = 'image'
        """,
    )


def pos_payment_currency_rate(env):
    """
    pos.payment#currency_rate was related to the order, it is now a stored field
    """
    cr = env.cr
    if openupgrade.column_exists(cr, "pos_payment", "currency_rate"):
        return
    openupgrade.logged_query(
        cr, "ALTER TABLE pos_payment ADD COLUMN currency_rate double precision"
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_payment pp
        SET currency_rate = po.currency_rate
        FROM pos_order po
        WHERE po.id = pp.pos_order_id
        """,
    )


def new_uuid_columns(env):
    """
    The python default of the new uuid fields is evaluated once by the ORM, which
    would give the same uuid to every existing row. Generate one per row.
    """
    cr = env.cr
    for table in (
        "product_attribute_custom_value",
        "pos_prep_line",
        "pos_prep_order",
    ):
        if not openupgrade.table_exists(cr, table):
            continue
        if not openupgrade.column_exists(cr, table, "uuid"):
            openupgrade.logged_query(cr, f"ALTER TABLE {table} ADD COLUMN uuid varchar")
        openupgrade.logged_query(
            cr, f"UPDATE {table} SET uuid = gen_random_uuid()::text WHERE uuid IS NULL"
        )


@openupgrade.migrate()
def migrate(env, version):
    move_modules(env)
    openupgrade.rename_fields(env, _renamed_fields)
    pos_config_journals(env)
    pos_payment_method_type(env)
    pos_payment_currency_rate(env)
    new_uuid_columns(env)
