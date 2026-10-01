# Copyright Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import os

from odoo import api
from odoo.tools import config

from odoo.addons.base.models.ir_module import IrModuleModule

_logger = logging.getLogger(__name__)

BLOCKLIST_OPTION = "openupgrade_auto_install_blocklist"
BLOCKLIST_ENVIRON = "OPENUPGRADE_AUTO_INSTALL_BLOCKLIST"


def _get_auto_install_blocklist():
    """
    Names of the modules that must never be auto-installed during the migration,
    from the config file option ``openupgrade_auto_install_blocklist`` and/or the
    environment variable ``OPENUPGRADE_AUTO_INSTALL_BLOCKLIST`` (comma separated)
    """
    names = set()
    for raw in (config.get(BLOCKLIST_OPTION) or "", os.environ.get(BLOCKLIST_ENVIRON)):
        for name in (raw or "").replace("\n", ",").split(","):
            if name.strip():
                names.add(name.strip())
    return names


@api.model
def _openupgrade_auto_install_blocked(self):
    """
    Return the uninstalled auto_install modules that must not be auto-installed:

    - modules without code in this version (removed modules whose record is still in
      the database with the auto_install flag and dependencies of the old version)
    - modules of the auto-install blocklist (see `_get_auto_install_blocklist`)
    - uninstalled modules depending (directly or not) on one of the above, as they
      can't be installed without them
    """
    cr = self.env.cr
    self.env["ir.module.module"].flush_model()
    self.env["ir.module.module.dependency"].flush_model()
    cr.execute(
        "SELECT name FROM ir_module_module "
        "WHERE state = 'uninstalled' AND auto_install"
    )
    names = {
        name for (name,) in cr.fetchall() if not self.get_module_info(name)
    } | _get_auto_install_blocklist()
    if not names:
        return self.browse()
    cr.execute(
        """
        WITH RECURSIVE blocked(name) AS (
            SELECT unnest(%s::varchar[])
            UNION
            SELECT m.name
            FROM ir_module_module m
            JOIN ir_module_module_dependency d ON d.module_id = m.id
            JOIN blocked b ON b.name = d.name
            WHERE m.state = 'uninstalled'
        )
        SELECT m.id
        FROM ir_module_module m
        JOIN blocked b ON b.name = m.name
        WHERE m.state = 'uninstalled' AND m.auto_install
        """,
        (sorted(names),),
    )
    return self.browse(row[0] for row in cr.fetchall())


@api.model
def update_list(self):
    """
    Mark auto_install modules as to install if all their dependencies are some kind of
    installed.
    Ignore localization modules that are set to auto_install, and the modules
    returned by `_openupgrade_auto_install_blocked`
    """
    result = IrModuleModule.update_list._original_method(self)
    blocklist = _get_auto_install_blocklist()
    # a module without code can't be installed, and a module of the blocklist must
    # not stay 'to install' (eg. from the database of a previous run) unless another
    # module being installed or upgraded requires it
    while True:
        self.env["ir.module.module"].flush_model()
        self.env.cr.execute(
            """
            SELECT m.id, m.name, EXISTS(
                SELECT FROM ir_module_module_dependency d
                JOIN ir_module_module dm ON dm.id = d.module_id
                WHERE d.name = m.name
                AND dm.state IN ('to install', 'to upgrade', 'installed')
            )
            FROM ir_module_module m WHERE m.state = 'to install'
            """
        )
        reset = self.browse(
            module_id
            for module_id, name, required in self.env.cr.fetchall()
            if not self.get_module_info(name) or (name in blocklist and not required)
        )
        if not reset:
            break
        _logger.info(
            "OpenUpgrade: resetting modules to uninstalled: %s",
            ", ".join(sorted(reset.mapped("name"))),
        )
        reset.write({"state": "uninstalled"})
    blocked = self._openupgrade_auto_install_blocked()
    if blocklist:
        _logger.info(
            "OpenUpgrade: auto-install blocklist active, not auto-installing: %s",
            ", ".join(sorted(blocked.mapped("name"))),
        )
    new_auto_install_modules = self.browse([])
    for module in self.env["ir.module.module"].search(
        [
            ("auto_install", "=", True),
            ("state", "=", "uninstalled"),
            ("name", "not like", ("l10n_%")),
            ("id", "not in", blocked.ids),
        ]
    ):
        if all(
            state in ("to upgrade", "to install", "installed")
            for state in module.dependencies_id.mapped("state")
        ):
            new_auto_install_modules |= module
    if new_auto_install_modules:
        new_auto_install_modules.button_install()
    return result


def button_install(self):
    """
    Don't let Odoo auto-install the modules returned by
    `_openupgrade_auto_install_blocked` (they are hidden from the auto_install
    search of the original method). Modules explicitly asked for, or required as a
    dependency of a module being installed, are still installed.
    """
    hidden = self._openupgrade_auto_install_blocked() - self
    if not hidden:
        return IrModuleModule.button_install._original_method(self)
    cr = self.env.cr
    cr.execute(
        "UPDATE ir_module_module SET auto_install = FALSE WHERE id IN %s",
        (tuple(hidden.ids),),
    )
    self.invalidate_model(["auto_install"])
    try:
        return IrModuleModule.button_install._original_method(self)
    finally:
        self.flush_model()
        cr.execute(
            "UPDATE ir_module_module SET auto_install = TRUE WHERE id IN %s",
            (tuple(hidden.ids),),
        )
        self.invalidate_model(["auto_install"])
        blocklist = _get_auto_install_blocklist()
        for module in hidden.filtered(
            lambda m: m.state == "to install" and m.name in blocklist
        ):
            _logger.warning(
                "OpenUpgrade: module %s is in the auto-install blocklist but is "
                "required by %s, installing it anyway",
                module.name,
                ", ".join(
                    sorted(
                        self.env["ir.module.module.dependency"]
                        .search(
                            [
                                ("name", "=", module.name),
                                (
                                    "module_id.state",
                                    "in",
                                    ("to install", "to upgrade", "installed"),
                                ),
                            ]
                        )
                        .module_id.mapped("name")
                    )
                ),
            )


def check_external_dependencies(self, module_name, newstate="to install"):
    try:
        IrModuleModule.check_external_dependencies._original_method(
            self, module_name, newstate=newstate
        )
    except AttributeError:  # pylint: disable=except-pass
        # this happens when a module is installed that doesn't exist in the new version
        pass


IrModuleModule._openupgrade_auto_install_blocked = _openupgrade_auto_install_blocked
update_list._original_method = IrModuleModule.update_list
IrModuleModule.update_list = update_list
button_install._original_method = IrModuleModule.button_install
IrModuleModule.button_install = button_install
check_external_dependencies._original_method = (
    IrModuleModule.check_external_dependencies
)
IrModuleModule.check_external_dependencies = check_external_dependencies
