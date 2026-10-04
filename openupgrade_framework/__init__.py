import logging
import os

from odoo.modules import get_module_path
from odoo.tools import config

from . import odoo_patch

# Odoo 20 no longer re-exports the convert_* helpers from odoo.tools (only
# convert_file is), but openupgradelib (load_data) still looks them up as
# tools.convert_xml_import / tools.convert_csv_import. Restore the aliases.
import odoo.tools as _tools  # noqa: E402
from odoo.tools import convert as _convert  # noqa: E402

for _name in ("convert_xml_import", "convert_csv_import", "convert_sql_import"):
    if not hasattr(_tools, _name) and hasattr(_convert, _name):
        setattr(_tools, _name, getattr(_convert, _name))


def _patch_update_module_moved_fields():
    """openupgradelib.update_module_moved_fields breaks with a UNIQUE (module,
    name) violation on ir_model_data when the new module has already reflected
    the field (the new owner loads before the old module, e.g. web_enterprise vs
    web_map). Make it tolerant: when the xmlid already exists in the new module
    the stale xmlid of the old module is dropped, else it is moved."""
    from openupgradelib import openupgrade as _ou

    if getattr(_ou.update_module_moved_fields, "_tolerant", False):
        return
    _original = _ou.update_module_moved_fields

    def update_module_moved_fields(cr, model, moved_fields, old_module, new_module):
        if isinstance(moved_fields, (list, tuple)) and moved_fields:
            cr.execute(
                """
                SELECT imd.id FROM ir_model_data imd
                JOIN ir_model_fields imf ON imf.id = imd.res_id
                WHERE imd.model = 'ir.model.fields' AND imd.module = %s
                    AND imf.model = %s AND imf.name IN %s
                    AND EXISTS (SELECT 1 FROM ir_model_data n
                        WHERE n.module = %s AND n.name = imd.name)
                """,
                (old_module, model, tuple(moved_fields), new_module),
            )
            ids = [r[0] for r in cr.fetchall()]
            if ids:
                _ou.logger.info(
                    "update_module_moved_fields: dropping stale xmlids %s of "
                    "module %s (already defined in %s)",
                    ids, old_module, new_module,
                )
                cr.execute("DELETE FROM ir_model_data WHERE id IN %s", (tuple(ids),))
        return _original(cr, model, moved_fields, old_module, new_module)

    update_module_moved_fields._tolerant = True
    _ou.update_module_moved_fields = update_module_moved_fields


try:
    _patch_update_module_moved_fields()
except Exception:  # pragma: no cover
    logging.getLogger(__name__).exception("cannot patch update_module_moved_fields")

if not config.get("upgrade_path"):
    path = get_module_path("openupgrade_scripts", display_warning=False)
    if path and os.path.isdir(os.path.join(path, "scripts")):
        logging.getLogger(__name__).info(
            "Setting upgrade_path to the scripts directory inside the module "
            "location of openupgrade_scripts"
        )
        # Odoo >= 19 expects a list here (see odoo.modules.module.initialize_sys_path)
        config["upgrade_path"] = [os.path.join(path, "scripts")]


def openupgrade_test(cls):
    """
    Set attributes on a test class necessary for the test framework
    Use as decorator on test classes in openupgrade_scripts/scripts/*/tests/test_*.py
    """
    tags = getattr(cls, "test_tags", None) or set()
    if "openupgrade" not in tags:
        tags.add("openupgrade")
    if not any(t.endswith("_install") for t in tags):
        tags.add("at_install")
    cls.test_tags = tags
    cls.test_module = cls.__module__.split(".")[2]
    cls.test_class = cls.__name__
    cls.test_sequence = 0
    return cls
