package main

import (
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
	"github.com/golang-migrate/migrate/v4"
	"github.com/golang-migrate/migrate/v4/database/mysql"
	"github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/database/sqlite3"
	_ "github.com/golang-migrate/migrate/v4/source/file"
	_ "github.com/jackc/pgx/v5/stdlib"
	_ "github.com/mattn/go-sqlite3"

	"lazyrag/core/log"
)

func main() {
	log.Init()

	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	cmd := os.Args[1]
	switch cmd {
	case "create":
		createCmd(os.Args[2:])
	case "up":
		upCmd(os.Args[2:])
	case "down":
		downCmd(os.Args[2:])
	case "goto":
		gotoCmd(os.Args[2:])
	case "version":
		versionCmd(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `dbmigrate: create and run SQL migrations.

Database: use the same DB as core. In Docker see docker-compose.yml service "core"
  (db service = Postgres 16; core uses ACL_DB_DRIVER=postgres, ACL_DB_DSN=...).

Env (defaults match core/main.go):
  ACL_DB_DRIVER   sqlite|postgres|mysql   (default: sqlite)
  ACL_DB_DSN      driver dsn             (default: ./acl.db when sqlite)
  MIGRATIONS_DIR  path to migrations dir  (default: ./migrations)

  Docker/compose example:
    ACL_DB_DRIVER=postgres
    ACL_DB_DSN="host=db user=app password=app dbname=app port=5432 sslmode=disable TimeZone=UTC"

Commands:
  create -name <snake_name>          create two files: <ts>_<name>.up.sql and .down.sql
  up [-n <steps>]                    apply all pending migrations (or N steps)
  down [-n <steps>]                  rollback 1 step (or N steps)
  goto -version <v>                  migrate up/down to a specific version
  version                            print current migration version
`)
}

func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func migrationsDir() string {
	return envOr("MIGRATIONS_DIR", "./migrations")
}

func dbConfigFromEnv() (driver, dsn string) {
	driver = envOr("ACL_DB_DRIVER", "sqlite")
	dsn = strings.TrimSpace(os.Getenv("ACL_DB_DSN"))
	if driver == "sqlite" && dsn == "" {
		dsn = "./acl.db"
	}
	return driver, dsn
}

func createCmd(args []string) {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	name := fs.String("name", "", "migration name, e.g. add_prompt_tables")
	_ = fs.Parse(args)
	if strings.TrimSpace(*name) == "" {
		log.Logger.Error().Msg("create: -name is required")
		os.Exit(2)
	}

	dir := migrationsDir()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		log.Logger.Error().Err(err).Msg("create: mkdir failed")
		os.Exit(1)
	}

	ts := time.Now().UTC().Format("20060102150405")
	base := fmt.Sprintf("%s_%s", ts, sanitizeName(*name))
	up := filepath.Join(dir, base+".up.sql")
	down := filepath.Join(dir, base+".down.sql")

	writeIfNotExists(up, fmt.Sprintf("-- %s\n-- +migrate Up\n\n", base))
	writeIfNotExists(down, fmt.Sprintf("-- %s\n-- +migrate Down\n\n", base))

	fmt.Println(up)
	fmt.Println(down)
}

func sanitizeName(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	s = strings.ReplaceAll(s, " ", "_")
	s = strings.ReplaceAll(s, "-", "_")
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '_' {
			b.WriteRune(r)
		}
	}
	out := b.String()
	out = strings.Trim(out, "_")
	if out == "" {
		return "migration"
	}
	return out
}

func writeIfNotExists(path, content string) {
	if _, err := os.Stat(path); err == nil {
		log.Logger.Error().Str("path", path).Msg("create: already exists")
		os.Exit(1)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		log.Logger.Error().Err(err).Str("path", path).Msg("create: write failed")
		os.Exit(1)
	}
}

func upCmd(args []string) {
	fs := flag.NewFlagSet("up", flag.ExitOnError)
	n := fs.Int("n", 0, "steps to apply (0 = all)")
	_ = fs.Parse(args)

	m := mustMigrator()
	defer closeMigrator(m)

	var err error
	if *n <= 0 {
		err = m.Up()
	} else {
		err = m.Steps(*n)
	}
	if err != nil && !errors.Is(err, migrate.ErrNoChange) {
		log.Logger.Error().Err(err).Msg("up failed")
		os.Exit(1)
	}
	log.Logger.Info().Msg("up ok")
}

func downCmd(args []string) {
	fs := flag.NewFlagSet("down", flag.ExitOnError)
	n := fs.Int("n", 1, "steps to rollback")
	_ = fs.Parse(args)

	m := mustMigrator()
	defer closeMigrator(m)

	if *n <= 0 {
		log.Logger.Error().Msg("down: -n must be > 0")
		os.Exit(2)
	}
	err := m.Steps(-*n)
	if err != nil && !errors.Is(err, migrate.ErrNoChange) {
		log.Logger.Error().Err(err).Msg("down failed")
		os.Exit(1)
	}
	log.Logger.Info().Msg("down ok")
}

func gotoCmd(args []string) {
	fs := flag.NewFlagSet("goto", flag.ExitOnError)
	v := fs.Uint("version", 0, "target version, e.g. 20260312093000")
	_ = fs.Parse(args)
	if *v == 0 {
		log.Logger.Error().Msg("goto: -version is required")
		os.Exit(2)
	}

	m := mustMigrator()
	defer closeMigrator(m)

	if err := m.Migrate(*v); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		log.Logger.Error().Err(err).Uint("version", *v).Msg("goto failed")
		os.Exit(1)
	}
	log.Logger.Info().Uint("version", *v).Msg("goto ok")
}

func versionCmd(args []string) {
	_ = args
	m := mustMigrator()
	defer closeMigrator(m)
	v, dirty, err := m.Version()
	if err != nil {
		if errors.Is(err, migrate.ErrNilVersion) {
			log.Logger.Info().Msg("version: 0 clean")
			return
		}
		log.Logger.Error().Err(err).Msg("version failed")
		os.Exit(1)
	}
	if dirty {
		log.Logger.Info().Uint("version", v).Msg("version: dirty")
		return
	}
	log.Logger.Info().Uint("version", v).Msg("version: clean")
}

func closeMigrator(m *migrate.Migrate) {
	if m == nil {
		return
	}
	_, _ = m.Close()
}

func mustMigrator() *migrate.Migrate {
	driver, dsn := dbConfigFromEnv()
	if strings.TrimSpace(dsn) == "" {
		log.Logger.Error().Msg("ACL_DB_DSN is empty")
		os.Exit(2)
	}

	mDir := migrationsDir()
	absDir, err := filepath.Abs(mDir)
	if err != nil {
		log.Logger.Error().Err(err).Str("dir", mDir).Msg("invalid MIGRATIONS_DIR")
		os.Exit(2)
	}
	sourceURL := "file://" + filepath.ToSlash(absDir)

	db, dbName := mustOpenSQL(driver, dsn)

	var mig *migrate.Migrate
	switch driver {
	case "sqlite":
		inst, err := sqlite3.WithInstance(db, &sqlite3.Config{
			DatabaseName: dbName,
		})
		if err != nil {
			log.Logger.Error().Err(err).Msg("sqlite3 instance failed")
			os.Exit(1)
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "sqlite3", inst)
		if err != nil {
			log.Logger.Error().Err(err).Msg("migrate init failed")
			os.Exit(1)
		}
	case "postgres":
		inst, err := postgres.WithInstance(db, &postgres.Config{})
		if err != nil {
			log.Logger.Error().Err(err).Msg("postgres instance failed")
			os.Exit(1)
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "postgres", inst)
		if err != nil {
			log.Logger.Error().Err(err).Msg("migrate init failed")
			os.Exit(1)
		}
	case "mysql":
		inst, err := mysql.WithInstance(db, &mysql.Config{})
		if err != nil {
			log.Logger.Error().Err(err).Msg("mysql instance failed")
			os.Exit(1)
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "mysql", inst)
		if err != nil {
			log.Logger.Error().Err(err).Msg("migrate init failed")
			os.Exit(1)
		}
	default:
		log.Logger.Error().Str("driver", driver).Msg("unsupported ACL_DB_DRIVER (use sqlite|postgres|mysql)")
		os.Exit(2)
	}

	return mig
}

func mustOpenSQL(driver, dsn string) (*sql.DB, string) {
	switch driver {
	case "sqlite":
		// golang-migrate 的 sqlite3 驱动使用 mattn/go-sqlite3。
		db, err := sql.Open("sqlite3", dsn)
		if err != nil {
			log.Logger.Error().Err(err).Msg("open sqlite failed")
			os.Exit(1)
		}
		return db, dsn
	case "postgres":
		// 使用 pgx 标准库；DSN 可为 URL 或 key=value，驱动名为 "pgx"。
		db, err := sql.Open("pgx", dsn)
		if err != nil {
			log.Logger.Error().Err(err).Msg("open postgres failed")
			os.Exit(1)
		}
		return db, ""
	case "mysql":
		db, err := sql.Open("mysql", dsn)
		if err != nil {
			log.Logger.Error().Err(err).Msg("open mysql failed")
			os.Exit(1)
		}
		return db, ""
	default:
		log.Logger.Error().Str("driver", driver).Msg("unsupported driver")
		os.Exit(2)
		return nil, ""
	}
}
