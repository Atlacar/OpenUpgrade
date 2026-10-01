# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _name_sql(cr, alias="a"):
    """account.asset#name became translatable: the column is jsonb after the module
    update (varchar before). Return an SQL expression giving the plain name."""
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'account_asset' AND column_name = 'name'
        """
    )
    row = cr.fetchone()
    if row and row[0] == "jsonb":
        return (
            f"COALESCE({alias}.name->>'en_US', "
            f"(SELECT value FROM jsonb_each_text({alias}.name) LIMIT 1))"
        )
    return f"{alias}.name"


def _company_dependent(value, company_id):
    """SQL jsonb value of a company dependent many2one."""
    return None if not value or not company_id else {str(company_id): value}


def _json(value):
    return None if value is None else json.dumps(value)


def _insert_model(cr, vals):
    columns = list(vals)
    cr.execute(
        "INSERT INTO account_depreciation_model ({}, create_uid, write_uid, "
        "create_date, write_date) VALUES ({}, 1, 1, now() at time zone 'UTC', "
        "now() at time zone 'UTC') RETURNING id".format(
            ", ".join(columns),
            ", ".join(
                "%s::jsonb" if c in ("journal_id",) else "%s" for c in columns
            ),
        ),
        [
            _json(vals[c]) if c in ("journal_id",) else vals[c]
            for c in columns
        ],
    )
    return cr.fetchone()[0]


def asset_models_to_depreciation_models(env):
    """19.0 asset models were account.asset records with state = 'model'; 20.0 has
    the dedicated model account.depreciation.model (prod: 9 models, 0 assets).

    - the model is copied (name kept as custom name, journal as company dependent
      value), its xmlids / chatter / attachments are moved to the new record;
    - account.account#asset_model_ids / create_asset become
      depreciation_model_id (first model of the account) and the accounts of the
      model become the accumulated depreciation / expense accounts of the account
      (the asset account of the model, if any, gets the model as default);
    - the old model rows are removed from account_asset.
    Returns {old model id: new depreciation model id}.
    """
    cr = env.cr
    name_sql = _name_sql(cr)
    cr.execute(
        f"""
        SELECT a.id, {name_sql}, a.company_id, a.active, a.method,
            a.method_number, a.method_period, a.method_progress_factor,
            a.prorata_computation_type, a.salvage_value_pct, a.journal_id,
            a.account_asset_id, a.account_depreciation_id,
            a.account_depreciation_expense_id
        FROM account_asset a
        WHERE a.state = 'model'
        ORDER BY a.id
        """
    )
    model_map = {}
    model_rows = {}
    for (
        old_id,
        name,
        company_id,
        active,
        method,
        method_number,
        method_period,
        factor,
        prorata,
        salvage_pct,
        journal_id,
        account_asset_id,
        depreciation_account_id,
        expense_account_id,
    ) in cr.fetchall():
        new_id = _insert_model(
            cr,
            {
                "name": name,
                "is_name_custom": True,
                "company_id": company_id,
                "active": True if active is None else active,
                "method": method or "linear",
                "method_mode": "duration",
                "method_number": method_number or 1,
                "method_period": method_period or "12",
                "method_progress_factor": factor or 0.0,
                "prorata_computation_type": prorata or "constant_periods",
                "salvage_value_percent": salvage_pct or 0.0,
                "journal_id": _company_dependent(journal_id, company_id),
            },
        )
        model_map[old_id] = new_id
        model_rows[old_id] = {
            "account_asset_id": account_asset_id,
            "depreciation_account_id": depreciation_account_id,
            "expense_account_id": expense_account_id,
        }
        cr.execute(
            """
            UPDATE ir_model_data SET model = 'account.depreciation.model', res_id = %s
            WHERE model = 'account.asset' AND res_id = %s
            """,
            (new_id, old_id),
        )
        cr.execute(
            """
            UPDATE mail_message SET model = 'account.depreciation.model', res_id = %s
            WHERE model = 'account.asset' AND res_id = %s
            """,
            (new_id, old_id),
        )
        cr.execute(
            """
            UPDATE mail_followers
            SET res_model = 'account.depreciation.model', res_id = %s
            WHERE res_model = 'account.asset' AND res_id = %s
            """,
            (new_id, old_id),
        )
        cr.execute(
            """
            UPDATE ir_attachment SET res_model = 'account.depreciation.model',
                res_id = %s
            WHERE res_model = 'account.asset' AND res_id = %s
            """,
            (new_id, old_id),
        )
        cr.execute(
            """
            UPDATE mail_activity
            SET res_model = 'account.depreciation.model', res_id = %s,
                res_model_id = (SELECT id FROM ir_model
                    WHERE model = 'account.depreciation.model')
            WHERE res_model = 'account.asset' AND res_id = %s
            """,
            (new_id, old_id),
        )
    if not model_map:
        return model_map, {}

    # account.account: first model of the m2m -> depreciation_model_id, and the
    # accounts of the model -> accounts of the fixed asset account
    cr.execute(
        """
        SELECT account_account_id, account_asset_id
        FROM account_account_account_asset_rel
        WHERE account_asset_id IN %s
        ORDER BY account_account_id, account_asset_id
        """,
        (tuple(model_map),),
    )
    done_accounts = set()
    for account_id, old_model_id in cr.fetchall():
        if account_id in done_accounts:
            continue
        done_accounts.add(account_id)
        row = model_rows[old_model_id]
        cr.execute(
            """
            UPDATE account_account
            SET depreciation_model_id = %s,
                asset_depreciation_account_id = COALESCE(
                    asset_depreciation_account_id, %s),
                asset_expense_account_id = COALESCE(asset_expense_account_id, %s)
            WHERE id = %s
            """,
            (
                model_map[old_model_id],
                row["depreciation_account_id"],
                row["expense_account_id"],
                account_id,
            ),
        )
    for old_model_id, row in model_rows.items():
        if row["account_asset_id"] and row["account_asset_id"] not in done_accounts:
            done_accounts.add(row["account_asset_id"])
            cr.execute(
                """
                UPDATE account_account
                SET depreciation_model_id = COALESCE(depreciation_model_id, %s),
                    asset_depreciation_account_id = COALESCE(
                        asset_depreciation_account_id, %s),
                    asset_expense_account_id = COALESCE(asset_expense_account_id, %s)
                WHERE id = %s
                """,
                (
                    model_map[old_model_id],
                    row["depreciation_account_id"],
                    row["expense_account_id"],
                    row["account_asset_id"],
                ),
            )
    _logger.info(
        "%s asset models converted to depreciation models, %s accounts updated",
        len(model_map),
        len(done_accounts),
    )
    return model_map, model_rows


def assets_to_asset_variants(env, model_map):
    """Every 19.0 asset (state != 'model') carried its own depreciation
    configuration. In 20.0 the asset is a container and the configuration lives in
    an account.asset.variant (main variant) pointing to an
    account.depreciation.model (method / duration / period / prorata). The
    variant keeps the state, journal, accounts, amounts, dates, and the parent
    variant (gross increase); the depreciation entries are linked to the variant.
    An asset whose configuration differs from the one of its model gets a model
    generated for that configuration. No change of any amount or entry."""
    cr = env.cr
    cr.execute(
        """
        SELECT a.id, a.model_id, a.company_id, a.state, a.journal_id, a.method,
            a.method_number, a.method_period, a.method_progress_factor,
            a.prorata_computation_type, a.prorata_date, a.salvage_value,
            a.book_value, a.already_depreciated_amount_import,
            a.asset_paused_days, a.disposal_date, a.net_gain_on_sale, a.parent_id,
            a.account_depreciation_id, a.account_depreciation_expense_id
        FROM account_asset a
        WHERE a.state != 'model' AND NOT EXISTS (
            SELECT 1 FROM account_asset_variant v WHERE v.asset_id = a.id)
        ORDER BY a.id
        """
    )
    assets = cr.fetchall()
    if not assets:
        return
    # configuration -> depreciation model
    cr.execute(
        """
        SELECT id, company_id, method, method_number, method_period,
            method_progress_factor, prorata_computation_type
        FROM account_depreciation_model
        ORDER BY id
        """
    )
    model_by_key = {}
    for row in cr.fetchall():
        key = (row[2], float(row[3]), row[4], row[5] or 0.0, row[6])
        model_by_key.setdefault(key, row[0])
    variant_of_asset = {}
    for (
        asset_id,
        old_model_id,
        company_id,
        state,
        journal_id,
        method,
        method_number,
        method_period,
        factor,
        prorata,
        prorata_date,
        salvage_value,
        book_value,
        already_depreciated,
        paused_days,
        disposal_date,
        net_gain,
        _parent_id,
        depreciation_account_id,
        expense_account_id,
    ) in assets:
        method = method or "linear"
        key = (
            method,
            float(method_number or 0),
            method_period or "12",
            factor or 0.0,
            prorata or "constant_periods",
        )
        model_id = model_by_key.get(key)
        if not model_id:
            model_id = _insert_model(
                cr,
                {
                    "name": "{} {} x {}".format(
                        method, int(method_number or 0), method_period or "12"
                    ),
                    "is_name_custom": False,
                    "company_id": None,
                    "active": True,
                    "method": method,
                    "method_mode": "duration",
                    "method_number": method_number or 1,
                    "method_period": method_period or "12",
                    "method_progress_factor": factor or 0.0,
                    "prorata_computation_type": prorata or "constant_periods",
                    "salvage_value_percent": 0.0,
                    "journal_id": _company_dependent(journal_id, company_id),
                },
            )
            model_by_key[key] = model_id
        cr.execute(
            """
            INSERT INTO account_asset_variant (
                asset_id, model_id, state, journal_id, prorata_computation_type,
                prorata_date, account_depreciation_id,
                account_depreciation_expense_id, book_value, salvage_value,
                already_depreciated_amount_import, asset_paused_days, disposal_date,
                net_gain_on_sale, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                1, 1, now() at time zone 'UTC', now() at time zone 'UTC')
            RETURNING id
            """,
            (
                asset_id,
                model_id,
                state,
                journal_id,
                prorata or "constant_periods",
                prorata_date,
                depreciation_account_id,
                expense_account_id,
                book_value,
                salvage_value,
                already_depreciated,
                paused_days,
                disposal_date,
                net_gain,
            ),
        )
        variant_of_asset[asset_id] = cr.fetchone()[0]
    for asset_id, *_rest in assets:
        parent_id = _rest[16]
        if parent_id and parent_id in variant_of_asset:
            cr.execute(
                "UPDATE account_asset_variant SET parent_id = %s WHERE id = %s",
                (variant_of_asset[parent_id], variant_of_asset[asset_id]),
            )
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_asset a SET main_variant_id = v.id
        FROM account_asset_variant v
        WHERE v.asset_id = a.id AND v.parent_id IS NULL AND a.main_variant_id IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_asset a SET main_variant_id = v.id
        FROM account_asset_variant v
        WHERE v.asset_id = a.id AND a.main_variant_id IS NULL
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_move m SET asset_variant_id = v.id
        FROM account_asset_variant v
        WHERE m.asset_id = v.asset_id AND m.asset_variant_id IS NULL
        """,
    )
    _logger.info("%s assets converted to asset + main variant", len(assets))


def remove_asset_model_rows(env):
    """Remove the old model rows (state = 'model') from account_asset, once
    everything pointing to them has been converted."""
    cr = env.cr
    cr.execute("SELECT id FROM account_asset WHERE state = 'model'")
    model_ids = [row[0] for row in cr.fetchall()]
    if not model_ids:
        return
    cr.execute("UPDATE account_asset SET model_id = NULL WHERE model_id IS NOT NULL")
    cr.execute("UPDATE account_asset SET parent_id = NULL WHERE parent_id IS NOT NULL")
    cr.execute(
        "DELETE FROM account_account_account_asset_rel WHERE account_asset_id IN %s",
        (tuple(model_ids),),
    )
    cr.execute("DELETE FROM account_asset WHERE id IN %s", (tuple(model_ids),))


@openupgrade.migrate()
def migrate(env, version):
    model_map, _rows = asset_models_to_depreciation_models(env)
    assets_to_asset_variants(env, model_map)
    remove_asset_model_rows(env)
