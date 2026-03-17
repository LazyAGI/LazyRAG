/*
 * MinIO Cloud Storage, (C) 2018 MinIO, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package target

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/minio/minio/pkg/event"
	"github.com/redis/go-redis/v9"
)

// Redis constants
const (
	RedisFormat     = "format"
	RedisAddress    = "address"
	RedisPassword   = "password"
	RedisKey        = "key"
	RedisQueueDir   = "queue_dir"
	RedisQueueLimit = "queue_limit"

	EnvRedisEnable     = "MINIO_NOTIFY_REDIS_ENABLE"
	EnvRedisFormat     = "MINIO_NOTIFY_REDIS_FORMAT"
	EnvRedisAddress    = "MINIO_NOTIFY_REDIS_ADDRESS"
	EnvRedisPassword   = "MINIO_NOTIFY_REDIS_PASSWORD"
	EnvRedisKey        = "MINIO_NOTIFY_REDIS_KEY"
	EnvRedisQueueDir   = "MINIO_NOTIFY_REDIS_QUEUE_DIR"
	EnvRedisQueueLimit = "MINIO_NOTIFY_REDIS_QUEUE_LIMIT"
)

// RedisArgs - Redis target arguments.
type RedisArgs struct {
	Enable     bool   `json:"enable"`
	Format     string `json:"format"`
	Addr       string `json:"address"`
	Password   string `json:"password"`
	Key        string `json:"key"`
	QueueDir   string `json:"queueDir"`
	QueueLimit uint64 `json:"queueLimit"`
}

// RedisAccessEvent holds event log data and timestamp
type RedisAccessEvent struct {
	Event     []event.Event
	EventTime string
}

// Validate RedisArgs fields
func (r RedisArgs) Validate() error {
	if !r.Enable {
		return nil
	}

	if r.Format != "" {
		f := strings.ToLower(r.Format)
		if f != event.NamespaceFormat && f != event.AccessFormat {
			return fmt.Errorf("unrecognized format")
		}
	}

	if r.Key == "" {
		return fmt.Errorf("empty key")
	}

	if r.QueueDir != "" {
		if !filepath.IsAbs(r.QueueDir) {
			return errors.New("queueDir path should be absolute")
		}
	}

	return nil
}

func (r RedisArgs) validateFormat(c *redis.Client) error {
	typeAvailable, err := c.Type(context.Background(), r.Key).Result()
	if err != nil {
		return err
	}

	if typeAvailable != "none" {
		expectedType := "hash"
		if r.Format == event.AccessFormat {
			expectedType = "list"
		}

		if typeAvailable != expectedType {
			return fmt.Errorf("expected type %v does not match with available type %v", expectedType, typeAvailable)
		}
	}

	return nil
}

// RedisTarget - Redis target.
type RedisTarget struct {
	id         event.TargetID
	args       RedisArgs
	rdc        *redis.Client
	store      Store
	firstPing  bool
	loggerOnce func(ctx context.Context, err error, id interface{}, errKind ...interface{})
}

// ID - returns target ID.
func (target *RedisTarget) ID() event.TargetID {
	return target.id
}

// HasQueueStore - Checks if the queueStore has been configured for the target
func (target *RedisTarget) HasQueueStore() bool {
	return target.store != nil
}

// IsActive - Return true if target is up and active
func (target *RedisTarget) IsActive() (bool, error) {
	defer func() {
		target.loggerOnce(context.Background(), nil, target.ID())
	}()

	if pingErr := target.rdc.Ping(context.Background()).Err(); pingErr != nil {
		if IsConnRefusedErr(pingErr) {
			return false, errNotConnected
		}
		return false, pingErr
	}
	return true, nil
}

// Save - saves the events to the store if questore is configured, which will be replayed when the redis connection is active.
func (target *RedisTarget) Save(eventData event.Event) error {
	if target.store != nil {
		return target.store.Put(eventData)
	}
	_, err := target.IsActive()
	if err != nil {
		return err
	}
	return target.send(eventData)
}

// send - sends an event to the redis.
func (target *RedisTarget) send(eventData event.Event) error {
	defer func() {
		target.loggerOnce(context.Background(), nil, target.ID())
	}()

	rdc := target.rdc
	if target.args.Format == event.NamespaceFormat {
		objectName, err := url.QueryUnescape(eventData.S3.Object.Key)
		if err != nil {
			return err
		}
		key := eventData.S3.Bucket.Name + "/" + objectName

		if eventData.EventName == event.ObjectRemovedDelete {
			err = rdc.HDel(context.Background(), target.args.Key, key).Err()
		} else {
			var data []byte
			if data, err = json.Marshal(struct{ Records []event.Event }{[]event.Event{eventData}}); err != nil {
				return err
			}
			err = rdc.HSet(context.Background(), target.args.Key, key, data).Err()
		}
		if err != nil {
			return err
		}
	}

	if target.args.Format == event.AccessFormat {
		data, err := json.Marshal([]RedisAccessEvent{{Event: []event.Event{eventData}, EventTime: eventData.EventTime}})
		if err != nil {
			return err
		}
		if _, err := rdc.RPush(context.Background(), target.args.Key, data).Result(); err != nil {
			return err
		}
	}

	return nil
}

// Send - reads an event from store and sends it to redis.
func (target *RedisTarget) Send(eventKey string) error {
	defer func() {
		target.loggerOnce(context.Background(), nil, target.ID())
	}()

	if pingErr := target.rdc.Ping(context.Background()).Err(); pingErr != nil {
		if IsConnRefusedErr(pingErr) {
			return errNotConnected
		}
		return pingErr
	}

	if !target.firstPing {
		if err := target.args.validateFormat(target.rdc); err != nil {
			if IsConnRefusedErr(err) {
				return errNotConnected
			}
			return err
		}
		target.firstPing = true
	}

	eventData, eErr := target.store.Get(eventKey)
	if eErr != nil {
		// The last event key in a successful batch will be sent in the channel atmost once by the replayEvents()
		// Such events will not exist and would've been already been sent successfully.
		if os.IsNotExist(eErr) {
			return nil
		}
		return eErr
	}

	if err := target.send(eventData); err != nil {
		if IsConnRefusedErr(err) {
			return errNotConnected
		}
		return err
	}

	// Delete the event from store.
	return target.store.Del(eventKey)
}

// Close - releases the resources used by the pool.
func (target *RedisTarget) Close() error {
	return target.rdc.Close()
}

// NewRedisTarget - creates new Redis target.
func NewRedisTarget(id string, args RedisArgs, doneCh <-chan struct{}, loggerOnce func(ctx context.Context, err error, id interface{}, errKind ...interface{}), test bool) (*RedisTarget, error) {
	var addr string
	if !strings.HasPrefix(args.Addr, "redis://") {
		addr = "redis://" + args.Addr
	}
	opt, err := redis.ParseURL(addr)
	if err != nil {
		return nil, err
	}
	if args.Password != "" {
		opt.Password = args.Password
	}

	rdc := redis.NewClient(opt)
	var store Store

	target := &RedisTarget{
		id:         event.TargetID{ID: id, Name: "redis"},
		args:       args,
		rdc:        rdc,
		loggerOnce: loggerOnce,
	}

	if args.QueueDir != "" {
		queueDir := filepath.Join(args.QueueDir, storePrefix+"-redis-"+id)
		store = NewQueueStore(queueDir, args.QueueLimit)
		if oErr := store.Open(); oErr != nil {
			target.loggerOnce(context.Background(), oErr, target.ID())
			return target, oErr
		}
		target.store = store
	}

	defer func() {
		target.loggerOnce(context.Background(), nil, target.ID())
	}()

	if pingErr := rdc.Ping(context.Background()).Err(); pingErr != nil {
		if target.store == nil || !(IsConnRefusedErr(pingErr) || IsConnResetErr(pingErr)) {
			target.loggerOnce(context.Background(), pingErr, target.ID())
			return target, pingErr
		}
	} else {
		if err := target.args.validateFormat(rdc); err != nil {
			target.loggerOnce(context.Background(), err, target.ID())
			return target, err
		}
		target.firstPing = true
	}

	if target.store != nil && !test {
		// Replays the events from the store.
		eventKeyCh := replayEvents(target.store, doneCh, target.loggerOnce, target.ID())
		// Start replaying events from the store.
		go sendEvents(target, eventKeyCh, doneCh, target.loggerOnce)
	}

	return target, nil
}
