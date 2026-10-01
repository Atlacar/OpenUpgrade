# Copyright 2026 Tecnativa - Pilar Vargas
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def preserve_footer_color_combination(env):
    for website in env["website"].search([]):
        env["website.assets"].with_context(
            website_id=website.id
        ).make_scss_customization(
            "/website/static/src/scss/options/colors/user_color_palette.scss",
            {"footer": 5},
        )


def sync_website_specific_assets(env):
    """
    Website-specific ir.asset records are COW copies of a generic asset (same
    key, see website ir.asset write()), created e.g. when a theme option such as
    the button ripple effect is switched on in the editor. Module updates only
    rewrite the generic record, so a copy keeps the 18.0 file path (e.g.
    website/static/src/js/content/ripple_effect.js, now
    website/static/src/interactions/ripple_effect.js) and the feature is lost.
    Re-sync the definition of the copies from their generic record, keeping the
    copy's active flag and sequence.
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


@openupgrade.migrate()
def migrate(env, version):
    sync_website_specific_assets(env)
    preserve_footer_color_combination(env)
    openupgrade.cow_templates_replicate_upstream(env.cr)
