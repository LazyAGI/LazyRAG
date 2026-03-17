package orm

import (
	"fmt"

	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"lazyrag/core/log"
)

// DB 封装 *gorm.DB，供 ACL 等模块使用。支持 PostgreSQL、SQLite、MySQL。
type DB struct {
	*gorm.DB
}

// Connect 使用的驱动名
const (
	DriverPostgres = "postgres"
	DriverSQLite   = "sqlite"
	DriverMySQL    = "mysql"
)

// Connect 打开数据库连接。driver: postgres / sqlite / mysql，dsn 格式依驱动而定。
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

// MustConnect 连接数据库，失败则打 Fatal 日志并退出，供 main 使用。
func MustConnect(driver, dsn string) *DB {
	db, err := Connect(driver, dsn)
	if err != nil {
		log.Logger.Fatal().Err(err).Str("driver", driver).Msg("orm: connect failed")
	}
	return db
}
