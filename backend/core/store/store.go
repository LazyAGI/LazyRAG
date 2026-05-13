// Package store text core text DB、Redis InitializetextRequestUsertext，text chat、doc、file text。
package store

import (
	"github.com/redis/go-redis/v9"
	"gorm.io/gorm"

	"lazyrag/core/common"
)

var (
	db        *gorm.DB
	lazyllmDB *gorm.DB
	rdb       *redis.Client
)

// Init Initializetext DB text Redis，text main textStarttext
func Init(database, lazyllmDatabase *gorm.DB, redisClient *redis.Client) {
	db = database
	if lazyllmDatabase != nil {
		lazyllmDB = lazyllmDatabase
	} else {
		lazyllmDB = database
	}
	rdb = redisClient
}

// DB text *gorm.DB
func DB() *gorm.DB { return db }

// LazyLLMDB text lazyllm text；text。
func LazyLLMDB() *gorm.DB {
	if lazyllmDB != nil {
		return lazyllmDB
	}
	return db
}

// Redis text *redis.Client，text nil（text）
func Redis() *redis.Client { return rdb }

// MustRedisFromEnv textCreate Redis text Ping，Failedtext panic，text main Initializetext
func MustRedisFromEnv() *redis.Client {
	return common.MustRedisFromEnv()
}
