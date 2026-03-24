// Package store 提供 core 内公用的 DB、Redis 初始化与访问以及请求用户上下文，供 chat、doc、file 等模块复用。
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

// Init 初始化全局 DB 与 Redis，由 main 在启动时调用
func Init(database, lazyllmDatabase *gorm.DB, redisClient *redis.Client) {
	db = database
	if lazyllmDatabase != nil {
		lazyllmDB = lazyllmDatabase
	} else {
		lazyllmDB = database
	}
	rdb = redisClient
}

// DB 返回全局 *gorm.DB
func DB() *gorm.DB { return db }

// LazyLLMDB 返回 lazyllm 只读库连接；未单独配置时回退到主库。
func LazyLLMDB() *gorm.DB {
	if lazyllmDB != nil {
		return lazyllmDB
	}
	return db
}

// Redis 返回全局 *redis.Client，可能为 nil（未配置时）
func Redis() *redis.Client { return rdb }

// MustRedisFromEnv 从环境变量创建 Redis 客户端并 Ping，失败则 panic，供 main 初始化使用
func MustRedisFromEnv() *redis.Client {
	return common.MustRedisFromEnv()
}
