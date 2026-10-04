"""Standalone check (no Odoo needed): python check_tracking_render.py

Loads ../20.0.1.19/post-migration.py with a stubbed openupgradelib and checks the
pure rendering functions against the markup of mail.mail_tracking_template.
"""
import datetime
import importlib.util
import os
import sys
import types

stub = types.ModuleType("openupgradelib")
stub.openupgrade = types.SimpleNamespace(migrate=lambda *a, **k: (lambda f: f))
sys.modules["openupgradelib"] = stub
path = os.path.join(os.path.dirname(__file__), "..", "20.0.1.19", "post-migration.py")
spec = importlib.util.spec_from_file_location("mail_post", path)
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


class Fmt:
    def yes_no(self, value):
        return "Yes" if value else "No"

    def number(self, value, integer):
        return "{:,}".format(value or 0) if integer else "{:,.2f}".format(value or 0)

    def amount(self, value, currency_id):
        return "$\u00a0{:,.2f}".format(value or 0)

    def datetime(self, value):
        return value.strftime("%b %d, %Y, %I:%M %p (UTC)")

    def date(self, value):
        return value.strftime("%b %d, %Y")


def vals(**kw):
    base = dict(integer=None, float=None, char=None, text=None, datetime=None)
    base.update(kw)
    return base


f = Fmt()
t = post.format_tracking_value
assert t("char", vals(), f) == "None"
assert t("selection", vals(char="Draft"), f) == "Draft"
assert t("selection", vals(char=""), f) == "None"
assert t("many2one", vals(char="A & B"), f) == "A & B"
assert t("integer", vals(integer=1234), f) == "1,234"
assert t("float", vals(float=0.5), f) == "0.50"
assert t("monetary", vals(float=1500), f, 33) == "$\u00a01,500.00"
assert t("monetary", vals(float=1500), f, None) == "1,500.00"
assert t("boolean", vals(integer=1), f) == "Yes"
assert t("boolean", vals(integer=0), f) == "No"
assert t("datetime", vals(), f) == "None"
dt = datetime.datetime(2026, 10, 1, 15, 4)
assert t("datetime", vals(datetime=dt), f) == "Oct 01, 2026, 03:04 PM (UTC)"
assert t("date", vals(datetime=dt), f) == "Oct 01, 2026"

html = post.render_tracking_html(
    [
        (None, "Draft", "Sent", "Status"),
        ("ACME", "None", "<b>x</b>", "Name & co"),
        (None, "$\xa010.00", "7", "Amount"),
    ]
)
assert html == (
    "<div>Draft → <b>Sent</b> <i>(Status)</i><br>"
    "<em>ACME: </em>None → <b>&lt;b&gt;x&lt;/b&gt;</b> <i>(Name &amp; co)</i><br>"
    "$&nbsp;10.00 → <b>7</b> <i>(Amount)</i>\n</div>"
), html
print("OK")
