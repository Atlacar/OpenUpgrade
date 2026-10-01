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
