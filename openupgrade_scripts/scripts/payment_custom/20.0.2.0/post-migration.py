# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # Applies the 20.0 values of the noupdate records of the Wire Transfer
    # provider (generic redirect form, live mode, messages) and links the Wire
    # Transfer payment method to its provider (payment.method#provider_id, which
    # the pre-migration of payment already filled from the old m2m).
    # The line setting payment_method_ids = None (an artefact of the
    # many2many -> one2many change) was removed from the noupdate file: it
    # must not be applied to the provider.
    openupgrade.load_data(env, "payment_custom", "20.0.2.0/noupdate_changes.xml")
