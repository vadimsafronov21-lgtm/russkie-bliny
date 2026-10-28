def business_dump(store):
    """Keep strict data/audit checks while allowing automatic view preferences."""
    return [line for line in store.db.iterdump()
            if not line.startswith('INSERT INTO "state" VALUES(\'ui_workspace:')
            and not line.startswith('INSERT INTO "state" VALUES(\'ui_preferences\'')]
