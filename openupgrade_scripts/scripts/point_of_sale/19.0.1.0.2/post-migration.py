# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

_deleted_xmlids = []


def pos_category_images(env):
    """
    v19 allows for bigger images, but we can't do better than putting the content of
    image_128 into image_512
    """
    env.cr.execute(
        """
        UPDATE ir_attachment
        SET res_field='image_512'
        WHERE
        res_model='pos.category'
        AND res_field='image_128'
        """
    )


def pos_config_create_sequences(env):
    """
    Create sequences for new fields by calling Odoo's function and deleting what
    already existed
    """
    sequence_fields = (
        "order_seq_id",
        "order_backend_seq_id",
        "order_line_seq_id",
        "device_seq_id",
    )
    to_delete = env["ir.sequence"]
    for pos_config in env["pos.config"].search([]):
        existing_sequences = {
            field_name: pos_config[field_name].id
            for field_name in pos_config._fields
            if field_name in sequence_fields and pos_config[field_name]
        }
        pos_config._create_sequences()
        to_delete += sum(
            (pos_config[field_name] for field_name in existing_sequences),
            env["ir.sequence"],
        )
        pos_config.write(existing_sequences)
    to_delete.unlink()


def pos_order_stock_reference_ids(env):
    """
    Fill pos.order#stock_reference_ids from procurement_group_id
    """
    env.cr.execute(
        """
        INSERT INTO
        stock_reference_pos_order_rel
        (pos_order_id, reference_id)
        SELECT
        id, procurement_group_id
        FROM pos_order
        WHERE procurement_group_id IS NOT NULL
        """
    )


def pos_order_state(env):
    """
    pos.order#state == invoiced has been removed, set orders with this state to 'done'
    as this is what _generate_pos_order_invoice does in v19 when it used 'invoiced' in
    v18
    """
    openupgrade.copy_columns(env.cr, {"pos_order": [("state", None, None)]})
    env.cr.execute("UPDATE pos_order SET state='done' WHERE state='invoiced'")


def uom_uom_is_pos_groupable(env):
    """
    Set uom.uom.is_pos_groupable from former uom category
    """
    env.cr.execute(
        f"""
        UPDATE uom_uom
        SET
        is_pos_groupable=uom_category.is_pos_groupable
        FROM
        uom_category
        WHERE
        uom_uom.{openupgrade.get_legacy_name("category_id")}=uom_category.id
        AND uom_category.is_pos_groupable
        """
    )


def pos_config_order_seq_id_placeholders(env):
    """
    v18 pos.config#sequence_id (renamed to order_seq_id) produced pos.order#name,
    its prefix/suffix could hold placeholders like 'Shop-%(y)s%(month)s%(day)s'.
    In v19 order_seq_id only feeds the integer pos.order#sequence_number:
    int(order_seq_id._next().removeprefix(prefix).removesuffix(suffix)) uses the
    raw prefix/suffix, so with placeholders every new order raises ValueError.
    Such configs get a fresh order sequence as _create_sequences creates it,
    continuing after the existing orders of the config; the old sequence is
    archived (unless still used by another sequence field of a config).
    """
    configs = env["pos.config"].with_context(active_test=False).search([])
    to_archive = env["ir.sequence"]
    for pos_config in configs:
        old = pos_config.order_seq_id
        if not old or not any("%(" in (part or "") for part in (old.prefix, old.suffix)):
            continue
        env.cr.execute(
            """
            SELECT GREATEST(COUNT(*), COALESCE(MAX(sequence_number), 0))
            FROM pos_order WHERE config_id = %s
            """,
            (pos_config.id,),
        )
        number_next = env.cr.fetchone()[0] + 1
        pos_config.order_seq_id = (
            env["ir.sequence"]
            .sudo()
            .create(
                {
                    "name": env._("POS order from config #%s", pos_config.id),
                    "padding": 6,
                    "code": "pos.order",
                    "company_id": pos_config.company_id.id,
                    "implementation": "no_gap",
                    "number_next": number_next,
                }
            )
        )
        to_archive |= old
        _logger.info(
            "pos.config %s: order sequence %s (prefix %r, suffix %r) replaced by %s "
            "(next number %s)",
            pos_config.id,
            old.id,
            old.prefix,
            old.suffix,
            pos_config.order_seq_id.id,
            number_next,
        )
    if to_archive:
        still_used = env["ir.sequence"]
        for fname in (
            "order_seq_id",
            "order_backend_seq_id",
            "order_line_seq_id",
            "device_seq_id",
        ):
            still_used |= configs.mapped(fname)
        (to_archive - still_used).write({"active": False})


def pos_config_order_backend_seq_id_next(env):
    """
    order_backend_seq_id is new in v19 (created by pos_config_create_sequences, starts
    at 1). It numbers pos.order#pos_reference / name / tracking_number of new orders:
    continue after the orders the config already has, as if the config had always
    numbered its orders with it.
    """
    env.cr.execute(
        """
        SELECT pc.id, pc.order_backend_seq_id, COUNT(po.id)
        FROM pos_config pc
        JOIN ir_sequence seq ON seq.id = pc.order_backend_seq_id
        JOIN pos_order po ON po.config_id = pc.id
        WHERE seq.number_next = 1
        GROUP BY pc.id, pc.order_backend_seq_id
        """
    )
    for _config_id, sequence_id, order_count in env.cr.fetchall():
        env["ir.sequence"].browse(sequence_id).sudo().number_next = order_count + 1


def pos_order_is_refund(env):
    """
    New stored field pos.order#is_refund (set by v19 when a refund is created):
    an order is a refund when one of its lines refunds another order line.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE pos_order po
        SET is_refund = EXISTS (
            SELECT 1 FROM pos_order_line pol
            WHERE pol.order_id = po.id AND pol.refunded_orderline_id IS NOT NULL
        )
        WHERE po.is_refund IS NULL OR NOT po.is_refund
        """,
    )


def pos_order_tracking_number(env):
    """
    pos.order#tracking_number ("Order Number" on receipts) was computed in v18
    (not stored):
        str((session_id.id % 10) * 100 + sequence_number % 100).zfill(3)
    v19 stores it when the order is created (int(next backend number) % 1000).
    Store the v18 value for existing orders, so reprinted receipts / the ticket
    screen show the number printed on the original receipt and it can be searched.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE pos_order
        SET tracking_number = LPAD(
            ((session_id %% 10) * 100 + COALESCE(sequence_number, 0) %% 100)::text,
            3,
            '0'
        )
        WHERE tracking_number IS NULL AND session_id IS NOT NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "point_of_sale", "19.0.1.0.2/noupdate_changes.xml")
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
    pos_category_images(env)
    pos_config_create_sequences(env)
    pos_config_order_seq_id_placeholders(env)
    pos_config_order_backend_seq_id_next(env)
    pos_order_stock_reference_ids(env)
    pos_order_state(env)
    pos_order_is_refund(env)
    pos_order_tracking_number(env)
    uom_uom_is_pos_groupable(env)
