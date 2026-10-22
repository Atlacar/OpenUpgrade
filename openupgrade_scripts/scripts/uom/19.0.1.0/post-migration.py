# Copyright 2025 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _uom_relative_uom_id_relative_factor(env):
    """
    UOM categories have been obsoleted, UOMs are a tree now with the reference
    unit as root and relative_factor giving the ratio to the UOM linked in
    relative_uom_id
    """

    Uom = env["uom.uom"]

    env.cr.execute(
        "SELECT res_id FROM ir_model_data WHERE "
        "model='uom.uom' AND module != '__export__'"
    )
    with_xml_id = Uom.browse(set(_id for (_id,) in env.cr.fetchall()))

    env.cr.execute(
        f"""
        SELECT
        array_agg(id),
        array_agg({openupgrade.get_legacy_name("factor")}),
        array_agg({openupgrade.get_legacy_name("uom_type")})
        FROM
        uom_uom
        WHERE {openupgrade.get_legacy_name("category_id")} IS NOT NULL
        GROUP BY {openupgrade.get_legacy_name("category_id")}
        """
    )
    for ids, factors, uom_types in env.cr.fetchall():
        uoms = Uom.browse(ids)
        uom2factor = dict(zip(uoms, factors, strict=True))
        uom2type = dict(zip(uoms, uom_types, strict=True))

        old_reference = uoms.filtered(
            lambda x, uom2type=uom2type: uom2type[x] == "reference"
        )

        for uom in uoms - old_reference - with_xml_id:
            # uoms with xmlid will be updated by the migration of the module
            # providing them
            relative_factor = (
                uom2factor[uom] if uom2type[uom] == "bigger" else (1 / uom2factor[uom])
            )

            uom.write(
                {
                    "relative_uom_id": old_reference,
                    "relative_factor": relative_factor,
                }
            )


def _uom_square_foot(env):
    """
    ft² had another xmlid in 18 (renamed in pre-migration), so it's missing from
    noupdate_changes.xml: hang it under m² like 19's data does
    """
    square_foot = env.ref("uom.product_uom_square_foot", raise_if_not_found=False)
    square_meter = env.ref("uom.product_uom_square_meter", raise_if_not_found=False)
    if not square_foot or not square_meter or square_foot.relative_uom_id:
        return
    category_id = openupgrade.get_legacy_name("category_id")
    factor = openupgrade.get_legacy_name("factor")
    env.cr.execute(
        f"""
        SELECT square_meter.{factor} / square_foot.{factor}
        FROM uom_uom square_foot
        JOIN uom_uom square_meter
        ON square_meter.{category_id} = square_foot.{category_id}
        WHERE square_foot.id = %s AND square_meter.id = %s
        """,
        (square_foot.id, square_meter.id),
    )
    row = env.cr.fetchone()
    if row:
        square_foot.write(
            {"relative_uom_id": square_meter.id, "relative_factor": row[0]}
        )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(
        env,
        "uom",
        "19.0.1.0/noupdate_changes.xml",
        xml_transformation_filename="19.0.1.0/noupdate_changes-transformation.xml",
    )
    _uom_relative_uom_id_relative_factor(env)
    _uom_square_foot(env)
