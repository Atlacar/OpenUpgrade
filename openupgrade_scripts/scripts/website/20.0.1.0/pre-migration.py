# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_added_fields = [
    (
        "manual_url",
        "website.menu",
        "website_menu",
        "char",
        None,
        "website",
    ),
]


def website_menu_manual_url(env):
    """website.menu#url is no longer stored: it is computed from the related
    page, or from the new stored field manual_url. Keep the URLs of the menus
    which are not linked to a page.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE website_menu
        SET manual_url = url
        WHERE page_id IS NULL AND COALESCE(url, '') NOT IN ('', '#')
        """,
    )


def ir_ui_view_visibility(env):
    """ir.ui.view#visibility is now required, the new key 'public' replaces
    the empty value
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_ui_view SET visibility = 'public'
        WHERE visibility IS NULL OR visibility = ''
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.add_fields(env, _added_fields)
    website_menu_manual_url(env)
    ir_ui_view_visibility(env)
    # website-specific copies of the views (copy on write) identical to their
    # generic view are reset to the 20.0 definition in end-migration
    openupgrade.cow_templates_mark_if_equal_to_upstream(env.cr)
