# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """The key 'inside' (document included in the quotation pdf) of
    product.document#attached_on_sale is removed: in 20.0 the documents with
    the keys 'hidden' and 'shown_on_product_page' are the ones inserted before
    the quotation table (see `_get_product_documents_before_and_after_quote`).
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_document SET attached_on_sale = 'hidden'
        WHERE attached_on_sale = 'inside'
        """,
    )
