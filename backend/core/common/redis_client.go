package common

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"

	"github.com/redis/go-redis/v9"
)

// MustRedisFromEnv textCreate Redis text Ping，Failedtext panic。
// text LAZYRAG_REDIS_URL（redis://user:pass@host:port/db）。
func MustRedisFromEnv() *redis.Client {
	if raw := strings.TrimSpace(os.Getenv("LAZYRAG_REDIS_URL")); raw != "" {
		u, err := url.Parse(raw)
		if err == nil && u.Scheme == "redis" {
			addr := u.Host
			pass, _ := u.User.Password()
			dbIndex := 0
			if p := strings.TrimPrefix(strings.TrimSpace(u.Path), "/"); p != "" {
				if n, err := strconv.Atoi(p); err == nil && n >= 0 {
					dbIndex = n
				}
			}
			opt := &redis.Options{Addr: addr, Password: pass, DB: dbIndex}
			c := redis.NewClient(opt)
			if err := c.Ping(context.Background()).Err(); err != nil {
				panic(fmt.Errorf("redis ping failed: %w", err))
			}
			return c
		}
	}

	addr := strings.TrimSpace(os.Getenv("REDIS_ADDR"))
	if addr == "" {
		addr = "redis:6379"
	}
	password := os.Getenv("REDIS_PASSWORD")
	opt := &redis.Options{Addr: addr, Password: password, DB: 0}
	c := redis.NewClient(opt)
	if err := c.Ping(context.Background()).Err(); err != nil {
		panic(fmt.Errorf("redis ping failed: %w", err))
	}
	return c
}
