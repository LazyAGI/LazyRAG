// Package migrate textStarttext SQL text（text dbmigrate upgrade text）。
// text：text dbmigrate migrate text migrations/*.sql，Starttext RunUp() text。
//
// text：golang-migrate text schema_migrations text（version, dirty），
// text；text。

package migrate

import (
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"strings"

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

// RunUp text migrations text .up.sql（text dbmigrate upgrade text）。Starttext，text。
// text ACL_DB_DSN text MIGRATIONS_DIR text nil。
func RunUp() error {
	driver := envOr("ACL_DB_DRIVER", "sqlite")
	dsn := strings.TrimSpace(os.Getenv("ACL_DB_DSN"))
	if driver == "sqlite" && dsn == "" {
		dsn = "./acl.db"
	}
	if dsn == "" {
		return nil
	}

	mDir := envOr("MIGRATIONS_DIR", "./migrations")
	absDir, err := filepath.Abs(mDir)
	if err != nil {
		return err
	}
	if _, err := os.Stat(absDir); os.IsNotExist(err) {
		log.Logger.Debug().Str("dir", absDir).Msg("migrations dir missing, skip RunUp")
		return nil
	}

	sourceURL := "file://" + filepath.ToSlash(absDir)
	db, dbName, err := openSQL(driver, dsn)
	if err != nil {
		return err
	}

	var mig *migrate.Migrate
	switch driver {
	case "sqlite":
		inst, err := sqlite3.WithInstance(db, &sqlite3.Config{DatabaseName: dbName})
		if err != nil {
			return err
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "sqlite3", inst)
		if err != nil {
			return err
		}
	case "postgres":
		inst, err := postgres.WithInstance(db, &postgres.Config{})
		if err != nil {
			return err
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "postgres", inst)
		if err != nil {
			return err
		}
	case "mysql":
		inst, err := mysql.WithInstance(db, &mysql.Config{})
		if err != nil {
			return err
		}
		mig, err = migrate.NewWithDatabaseInstance(sourceURL, "mysql", inst)
		if err != nil {
			return err
		}
	default:
		return nil
	}
	defer func() { _, _ = mig.Close() }()

	if err := mig.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	log.Logger.Info().Str("dir", absDir).Msg("SQL migrations applied")
	return nil
}

func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func openSQL(driver, dsn string) (*sql.DB, string, error) {
	switch driver {
	case "sqlite":
		db, err := sql.Open("sqlite3", dsn)
		if err != nil {
			return nil, "", err
		}
		return db, dsn, nil
	case "postgres":
		db, err := sql.Open("pgx", dsn)
		if err != nil {
			return nil, "", err
		}
		return db, "", nil
	case "mysql":
		db, err := sql.Open("mysql", dsn)
		if err != nil {
			return nil, "", err
		}
		return db, "", nil
	default:
		return nil, "", nil
	}
}
