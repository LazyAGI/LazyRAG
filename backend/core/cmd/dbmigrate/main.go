package main

import (
	"context"
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
	migratepostgres "github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/database/sqlite3"
	_ "github.com/golang-migrate/migrate/v4/source/file"
	_ "github.com/jackc/pgx/v5/stdlib"
	_ "github.com/mattn/go-sqlite3"
	gormpostgres "gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"lazyrag/core/common/orm"
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
	case "migrate":
		migrateCmd(os.Args[2:])
	case "upgrade":
		upCmd(os.Args[2:])
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
	case "force":
		forceCmd(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `dbmigrate: SQL migrations (类似 Flask-Migrate: migrate 生成脚本, upgrade 应用).

  Flask 对照:
    flask db migrate [-m "msg"]  →  dbmigrate migrate [-m "msg"]
    flask db upgrade             →  dbmigrate upgrade  或  core 启动时自动执行 RunUp()

Env: ACL_DB_DRIVER, ACL_DB_DSN, MIGRATIONS_DIR (default: ./migrations)

Commands:
  migrate [-m "message"]         生成迁移脚本（根据 orm/models 生成 DDL，需 Postgres + ACL_DB_DSN）
  upgrade                       应用所有未执行的迁移（修改数据库）
  create -name <name> [-with-ddl]  手动创建迁移文件（可选 -with-ddl 自动填 DDL）
  up [-n <steps>]               同 upgrade；-n 指定步数
  down [-n <steps>]              回滚 N 步
  goto -version <v>              迁移到指定版本
  version                        当前迁移版本
  force -version <v>              将版本表设为指定版本并清除 dirty（修复失败迁移后使用）
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

// migrateCmd 对应 Flask 的 flask db migrate：生成带 DDL 的迁移脚本（-m 可选描述）。
func migrateCmd(args []string) {
	fs := flag.NewFlagSet("migrate", flag.ExitOnError)
	msg := fs.String("m", "auto", "migration message (used as migration name)")
	_ = fs.Parse(args)
	name := strings.TrimSpace(*msg)
	if name == "" {
		name = "auto"
	}
	createCmdWith(sanitizeName(name), true)
}

func createCmd(args []string) {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	name := fs.String("name", "", "migration name, e.g. init or add_xxx")
	withDDL := fs.Bool("with-ddl", false, "generate full CREATE TABLE from orm/models (requires postgres + ACL_DB_DSN)")
	_ = fs.Parse(args)
	if strings.TrimSpace(*name) == "" {
		log.Logger.Error().Msg("create: -name is required")
		os.Exit(2)
	}
	createCmdWith(sanitizeName(*name), *withDDL)
}

func createCmdWith(name string, withDDL bool) {
	dir := migrationsDir()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		log.Logger.Error().Err(err).Msg("create: mkdir failed")
		os.Exit(1)
	}

	ts := time.Now().UTC().Format("20060102150405")
	base := fmt.Sprintf("%s_%s", ts, name)
	upPath := filepath.Join(dir, base+".up.sql")
	downPath := filepath.Join(dir, base+".down.sql")

	var upContent, downContent string
	if withDDL {
		driver, dsn := dbConfigFromEnv()
		if driver != "postgres" || strings.TrimSpace(dsn) == "" {
			log.Logger.Error().Msg("create -with-ddl requires ACL_DB_DRIVER=postgres and ACL_DB_DSN")
			os.Exit(2)
		}
		upSQL, downSQL, err := capturePostgresDDL(dsn)
		if err != nil {
			log.Logger.Error().Err(err).Msg("capture DDL failed")
			os.Exit(1)
		}
		upContent = fmt.Sprintf("-- %s\n-- +migrate Up\n\n%s", base, upSQL)
		downContent = fmt.Sprintf("-- %s\n-- +migrate Down\n\n%s", base, downSQL)
	} else {
		upContent = fmt.Sprintf("-- %s\n-- +migrate Up\n-- 在此下方填写 DDL，或使用 create -name xxx -with-ddl 自动生成。\n\n", base)
		downContent = fmt.Sprintf("-- %s\n-- +migrate Down\n-- 在此下方填写回滚 SQL。\n\n", base)
	}

	writeIfNotExists(upPath, upContent)
	writeIfNotExists(downPath, downContent)
	fmt.Println(upPath)
	fmt.Println(downPath)
}

// capturePostgresDDL 连接 Postgres，用 GORM 建表并捕获 SQL，返回 up（CREATE TABLE）与 down（DROP TABLE）。
func capturePostgresDDL(dsn string) (upSQL, downSQL string, err error) {
	var statements []string
	recorder := &sqlRecorder{collect: &statements}
	cfg := &gorm.Config{Logger: recorder}
	db, err := gorm.Open(gormpostgres.Open(dsn), cfg)
	if err != nil {
		return "", "", err
	}
	sqlDB, _ := db.DB()
	if sqlDB != nil {
		defer sqlDB.Close()
	}
	for _, m := range orm.AllModelsForDDL() {
		if err := db.Migrator().CreateTable(m); err != nil {
			return "", "", err
		}
	}
	var up strings.Builder
	for _, s := range statements {
		up.WriteString(s)
		if !strings.HasSuffix(strings.TrimSpace(s), ";") {
			up.WriteString(";")
		}
		up.WriteString("\n")
	}
	tables := orm.TableNamesForDDL()
	var down strings.Builder
	for i := len(tables) - 1; i >= 0; i-- {
		down.WriteString("DROP TABLE IF EXISTS ")
		down.WriteString(tables[i])
		down.WriteString(" CASCADE;\n")
	}
	return up.String(), down.String(), nil
}

type sqlRecorder struct {
	collect *[]string
}

func (s *sqlRecorder) LogMode(logger.LogLevel) logger.Interface { return s }

func (s *sqlRecorder) Info(context.Context, string, ...interface{})  {}
func (s *sqlRecorder) Warn(context.Context, string, ...interface{})  {}
func (s *sqlRecorder) Error(context.Context, string, ...interface{}) {}

func (s *sqlRecorder) Trace(ctx context.Context, begin time.Time, fc func() (string, int64), err error) {
	sql, _ := fc()
	sql = strings.TrimSpace(sql)
	if sql != "" {
		*s.collect = append(*s.collect, sql)
	}
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

// forceCmd 将 schema_migrations 设为指定版本并清除 dirty，用于修复 "Dirty database version" 报错。
// 仅在确认数据库实际状态与该版本一致时使用（例如表已存在且与迁移一致）。
func forceCmd(args []string) {
	fs := flag.NewFlagSet("force", flag.ExitOnError)
	v := fs.Uint("version", 0, "version to set, e.g. 20260315095955")
	_ = fs.Parse(args)
	if *v == 0 {
		log.Logger.Error().Msg("force: -version is required (e.g. 20260315095955)")
		os.Exit(2)
	}
	m := mustMigrator()
	defer closeMigrator(m)
	if err := m.Force(int(*v)); err != nil {
		log.Logger.Error().Err(err).Uint("version", *v).Msg("force failed")
		os.Exit(1)
	}
	log.Logger.Info().Uint("version", *v).Msg("force ok")
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
		inst, err := migratepostgres.WithInstance(db, &migratepostgres.Config{})
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
