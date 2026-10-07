"""PostgreSQL 18 stores NOT NULL as named constraints (pg_constraint.contype 'n').

openupgradelib.openupgrade.lift_constraints() selects every constraint on the
column, so on PostgreSQL 18 it also tries to drop "<table>_<column>_not_null"
together with the primary key in one ALTER TABLE, which fails with
'column "id" is in a primary key' (e.g. stock_account 19.0.1.1 post-migration).
NOT NULL is not a constraint to lift: same query, without contype 'n'.
"""

from openupgradelib import openupgrade
from psycopg2.extensions import AsIs


def lift_constraints(cr, table, column, cascade=False):
    cr.execute(
        "select relname, array_agg(conname) from "
        "(select t1.relname, c.conname "
        "from pg_constraint c "
        "join pg_attribute a "
        "on c.confrelid=a.attrelid and a.attnum=any(c.conkey) "
        "join pg_class t on t.oid=a.attrelid "
        "join pg_class t1 on t1.oid=c.conrelid "
        "where t.relname=%(table)s and attname=%(column)s and c.contype <> 'n' "
        "union select t.relname, c.conname "
        "from pg_constraint c "
        "join pg_attribute a "
        "on c.conrelid=a.attrelid and a.attnum=any(c.conkey) "
        "join pg_class t on t.oid=a.attrelid "
        "where relname=%(table)s and attname=%(column)s and c.contype <> 'n') in_out "
        "group by relname",
        {
            "table": table,
            "column": column,
        },
    )
    for table, constraints in cr.fetchall():
        cr.execute(
            "alter table %s drop constraint if exists %s",
            (
                AsIs(table),
                AsIs(
                    ", drop constraint if exists ".join(
                        (constraint if not cascade else (constraint + " cascade"))
                        for constraint in constraints
                    )
                ),
            ),
        )


openupgrade.lift_constraints = lift_constraints
