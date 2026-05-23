#!/usr/bin/env python3
"""
Migration: Add UNIQUE constraint on (trigger_id, evaluation_time) to evaluations table.
SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we use the recreate-table approach.
"""

import sqlite3
import os

DB_PATH = "data/triggers.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("ℹ️  Database does not exist yet, no migration needed.")
        return

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    c = conn.cursor()

    # Check if unique index already exists
    c.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND tbl_name = 'evaluations'
        AND sql LIKE '%UNIQUE%'
    """)
    existing = c.fetchall()
    if existing:
        print("✅ UNIQUE constraint already exists on evaluations table, skipping migration.")
        conn.close()
        return

    print("🔧 Adding UNIQUE constraint on (trigger_id, evaluation_time)...")

    # SQLite approach: create new table, copy data, drop old, rename new
    c.execute("""
        CREATE TABLE evaluations_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_id INTEGER NOT NULL,
            evaluation_time TEXT NOT NULL,
            price_at_eval REAL,
            open_price REAL,
            result TEXT NOT NULL,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trigger_id) REFERENCES triggers(id),
            UNIQUE(trigger_id, evaluation_time)
        )
    """)

    # Copy existing data (if any duplicates exist, they'll fail — but shouldn't at this point)
    c.execute("""
        INSERT INTO evaluations_new (id, trigger_id, evaluation_time, price_at_eval, open_price, result, evaluated_at)
        SELECT id, trigger_id, evaluation_time, price_at_eval, open_price, result, evaluated_at
        FROM evaluations
    """)

    c.execute("DROP TABLE evaluations")
    c.execute("ALTER TABLE evaluations_new RENAME TO evaluations")

    conn.commit()
    conn.close()
    print("✅ Migration complete: UNIQUE(trigger_id, evaluation_time) added.")

if __name__ == "__main__":
    migrate()
