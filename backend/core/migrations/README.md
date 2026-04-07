## SQL migrations

This directory contains versioned SQL migrations executed by `cmd/dbmigrate`.

Because SQL differs between SQLite/Postgres/MySQL (JSON types, AUTO INCREMENT, etc.),
we keep **driver-specific subdirectories** and select them via `MIGRATIONS_DIR`.

### Naming

Each migration must include two files:

- `<version>_<name>.up.sql`
- `<version>_<name>.down.sql`

Where:
- `<version>` is a UTC timestamp like `20260312093000` (YYYYMMDDhhmmss)
- `<name>` is a short snake_case description.

### Create a new migration

From `LazyRAG/backend/core` (choose a driver dir):

```powershell
$env:MIGRATIONS_DIR=".\migrations\sqlite"
go run .\cmd\dbmigrate create -name add_prompt_tables
```

### Apply / rollback

```powershell
$env:ACL_DB_DRIVER="sqlite"
$env:ACL_DB_DSN=".\acl.db"
$env:MIGRATIONS_DIR=".\migrations\sqlite"

go run .\cmd\dbmigrate up
go run .\cmd\dbmigrate down -n 1
go run .\cmd\dbmigrate version
```

