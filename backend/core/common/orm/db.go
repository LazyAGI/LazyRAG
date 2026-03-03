package orm

import (
	"fmt"
	"log"

	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

// DB wraps *gorm.DB for ACL and other modules. Supports PostgreSQL, SQLite, MySQL.
type DB struct {
	*gorm.DB
}

// Driver names for Connect.
const (
	DriverPostgres = "postgres"
	DriverSQLite   = "sqlite"
	DriverMySQL    = "mysql"
)

// Connect opens a database connection. driver: postgres, sqlite, mysql. dsn format depends on driver.
func Connect(driver, dsn string) (*DB, error) {
	var dialector gorm.Dialector
	switch driver {
	case DriverPostgres:
		dialector = postgres.Open(dsn)
	case DriverSQLite:
		dialector = sqlite.Open(dsn)
	case DriverMySQL:
		dialector = mysql.Open(dsn)
	default:
		return nil, fmt.Errorf("unsupported driver: %s (use postgres, sqlite, mysql)", driver)
	}
	db, err := gorm.Open(dialector, &gorm.Config{})
	if err != nil {
		return nil, err
	}
	return &DB{DB: db}, nil
}

// MigrateACL runs auto-migration for ACL-related tables.
func (db *DB) MigrateACL() error {
	return db.AutoMigrate(
		&VisibilityModel{},
		&ACLModel{},
		&KBModel{},
		&UserGroupModel{},
	)
}

// MustConnect connects or logs fatal. Useful for main.
func MustConnect(driver, dsn string) *DB {
	db, err := Connect(driver, dsn)
	if err != nil {
		log.Fatalf("orm: connect failed: %v", err)
	}
	return db
}
