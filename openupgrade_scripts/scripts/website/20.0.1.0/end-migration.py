# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def sync_website_specific_assets(env):
    """
    Website-specific ir.asset records are COW copies of a generic asset (same
    key, see website ir.asset write()), created e.g. when a theme option is
    switched on in the editor. Module updates only rewrite the generic record,
    so a copy keeps the 19.0 file path and the feature is lost when the file
    moved. Re-sync the definition of the copies from their generic record,
    keeping the copy's active flag and sequence.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_asset specific
        SET bundle = generic.bundle,
            directive = generic.directive,
            path = generic.path,
            target = generic.target
        FROM ir_asset generic
        JOIN ir_model_data imd
            ON imd.model = 'ir.asset'
            AND imd.res_id = generic.id
            AND imd.module || '.' || imd.name = generic.key
        WHERE specific.website_id IS NOT NULL
            AND generic.website_id IS NULL
            AND specific.key = generic.key
            AND (specific.bundle, specific.directive, specific.path, specific.target)
                IS DISTINCT FROM
                (generic.bundle, generic.directive, generic.path, generic.target)
        """,
    )


def backfill_published_date(env):
    """website.published.mixin has two new fields, publish_on (scheduled
    publication) and published_date, which is stamped when a record gets
    published. Records published before the migration get a date, otherwise
    unpublishing and publishing them again would be seen as a first
    publication (chatter notification of the publish hook).
    """
    for model_name in sorted(env.registry):
        model = env.registry[model_name]
        if model._abstract or model._transient or not model._auto:
            continue
        fields = model._fields
        if not (
            {"is_published", "publish_on", "published_date"} <= set(fields)
            and fields["published_date"].store
            and fields["is_published"].store
        ):
            continue
        table = model._table
        if not (
            openupgrade.column_exists(env.cr, table, "published_date")
            and openupgrade.column_exists(env.cr, table, "is_published")
        ):
            continue
        date_expr = (
            "COALESCE(create_date, NOW() AT TIME ZONE 'UTC')"
            if openupgrade.column_exists(env.cr, table, "create_date")
            else "NOW() AT TIME ZONE 'UTC'"
        )
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE "{table}"
            SET published_date = {date_expr}
            WHERE is_published IS TRUE AND published_date IS NULL
            """,
        )


@openupgrade.migrate()
def migrate(env, version):
    sync_website_specific_assets(env)
    openupgrade.cow_templates_replicate_upstream(env.cr)
    backfill_published_date(env)
