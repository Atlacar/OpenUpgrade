# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def pos_prep_stage_displays(env):
    """
    pos.prep.stage#prep_display_id (many2one) became the many2many
    pos.prep.stage#prep_display_ids / pos.prep.display#stage_ids
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "pos_prep_stage", "prep_display_id"):
        return
    field = env["pos.prep.display"]._fields["stage_ids"]
    openupgrade.logged_query(
        cr,
        f"""
        INSERT INTO {field.relation} ({field.column1}, {field.column2})
        SELECT prep_display_id, id
        FROM pos_prep_stage
        WHERE prep_display_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )


def pos_prep_state_to_line(env):
    """
    pos.prep.state (one row per preparation line and stage) is merged in
    pos.prep.line: the stage, todo and last_stage_change of a line are fields of the
    line. Keep the most recent state of each line.
    """
    cr = env.cr
    if not openupgrade.table_exists(cr, "pos_prep_state"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE pos_prep_line pl
        SET stage_id = ps.stage_id,
            todo = ps.todo,
            last_stage_change = ps.last_stage_change
        FROM (
            SELECT DISTINCT ON (prep_line_id)
                prep_line_id, stage_id, todo, last_stage_change
            FROM pos_prep_state
            ORDER BY prep_line_id, last_stage_change DESC NULLS LAST, id DESC
        ) ps
        WHERE ps.prep_line_id = pl.id
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    pos_prep_stage_displays(env)
    pos_prep_state_to_line(env)
