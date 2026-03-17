/*
 *	api-router-customize-transform.go 是datalake自定义的service的API,
 *  业务接口和minio 本身(实际是 juicefs-gateway --> minio-gateway) 在同一个进程运行:
 *	1. transform api: 将已存在的文件转化为特定格式
 */

package cmd

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	xhttp "github.com/minio/minio/cmd/http"
	"github.com/minio/minio/cmd/logger"
	"github.com/minio/minio/pkg/console"
	iampolicy "github.com/minio/minio/pkg/iam/policy"

	"github.com/gocelery/gocelery"
	"github.com/gomodule/redigo/redis"
)

func (api customAPIHandlers) TransformFileHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("TransformFileHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "TransformFile")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	contentType := r.Header.Get("Content-Type")
	if strings.HasPrefix(contentType, "multipart/form-data") {
		if err := r.ParseMultipartForm(32 << 20); err != nil {
			console.Errorf("form value invalid, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
			writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
			return
		}
	} else {
		if err := r.ParseForm(); err != nil {
			console.Errorf("form value invalid, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
			writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
			return
		}
	}
	formValue := ""
	for key, values := range r.Form {
		formValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("TransformFileHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, formValue)

	if getRequestAuthType(r) != authTypeDatalake {
		console.Errorf("invalid sensetime header, request_id: %s, type: %v", w.Header().Get(xhttp.AmzRequestID), getRequestAuthType(r))
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}
	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Transform cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	bucket := globalCustomizedDatalakeBucket
	id := r.FormValue("file_id")
	targettype := r.FormValue("target_type")
	targetEnum, ok := transformValidType[targettype]
	if !ok {
		console.Errorf("invalid target type, request_id: %s, trace_id: %s, err: %v, file_id: %s, target_type: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id, targettype)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}

	object, err := getFileObjectName(id, user)
	if err != nil {
		console.Errorf("calculate object name err, request_id: %s, trace_id: %s, err: %v, file_id: %s, user_id: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id, getUserPath(user))
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	if strings.HasPrefix(object, "/") {
		console.Errorf("invalid object name, request_id: %s, trace_id: %s, err: %v, file_id: %s, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	// 操作者是否有操作权限
	if err := isDatalakeActionAllowed(ctx, bucket, object, r, iampolicy.GetObjectAction); err != ErrNone {
		console.Errorf("no get authorization, err: %v, request_id: %s, trace_id: %s, object: %s, user_id: %s",
			err, w.Header().Get(xhttp.AmzRequestID), user.TraceID, object, getUserPath(user))
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrUnauthorizedAccess), r.URL)
		return
	}

	filetype := strings.TrimPrefix(ext(object), ".")
	if _, ok = transformValidFromType[filetype]; !ok {
		console.Errorf("invalid original type, request_id: %s, trace_id: %s, err: %v, file_id: %s, origin_type: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id, filetype)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}

	getObjectInfo := datalakeAPI.GetObjectInfo

	opts, err := getOpts(ctx, r, bucket, object)
	if err != nil {
		console.Errorf("get object opts err, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	objInfo, err := getObjectInfo(ctx, bucket, object, opts)
	if err != nil {
		console.Errorf("get object err, request_id: %s, trace_id: %s, err: %v, object: %s, ops: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrNoSuchKey), r.URL)
		return
	}
	mdata, _ := parseQuery(objInfo.UserTags)
	createdTime, _ := strconv.ParseInt(mdata["created_at"], 10, 64)
	_, filename := extractFileMetas(object, user)
	etag := objInfo.ETag

	// 1. 生成固定目标object，首先查看目标object是否存在，存在则直接返回
	targetObject := strings.Join([]string{strings.TrimSuffix(object, filetype), targettype}, "")
	targetID, _, err := calculateFilePath(targetObject)
	if err != nil {
		console.Errorf("calculateFilePath err, request_id: %s, trace_id: %s, err: %v, object: %s, user_id: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, targetObject, getUserPath(user))
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	newOpts, err := getOpts(ctx, r, bucket, targetObject)
	if err != nil {
		console.Errorf("get object opts err, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	targetInfo, err := getObjectInfo(ctx, bucket, targetObject, newOpts)

	rs := struct {
		ID             string `json:"id"`
		TargetType     string `json:"target_type"`
		Filename       string `json:"filename"`
		TargetID       string `json:"target_id"`
		TargetFilename string `json:"target_filename"`
		Done           bool   `json:"done"`
	}{
		ID:             id,
		TargetType:     targettype,
		Filename:       object,
		TargetID:       targetID,
		TargetFilename: targetObject,
	}

	if err == nil && targetInfo.Size > 0 {
		rs.Done = true
		resp, err := json.Marshal(rs)
		if err != nil {
			console.Errorf("marshal transform err, request_id: %s, trace_id: %s, err: %v, res: %v",
				w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, rs)
			customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
			return
		}
		writeSuccessResponseJSON(w, resp)
		return
	}

	// 2. 否则尝试向celery投递任务，注意相同的object, filename, targetObject, createTime幂等
	celeryMeta := celeryMeta{
		CreateAt: &createdTime,
	}
	if len(etag) > 0 {
		celeryMeta.Etag = &etag
	}
	celeryParams := celeryParams{
		TaskType:       transformTaskType,
		SourceFileURL:  object,
		SourceFileName: filename,
		TargetFileType: targetEnum,
		TargetFileURL:  targetObject,
		celeryMeta:     celeryMeta,
	}
	if err := api.launchCeleryTask(celeryParams); err != nil {
		console.Errorf("launch celery task err, request_id: %s, trace_id: %s, err: %v, res: %v, params: %+v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, rs, celeryParams)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	resp, err = json.Marshal(rs)
	if err != nil {
		console.Errorf("marshal transform err, request_id: %s, trace_id: %s, err: %v, res: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, rs)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	writeSuccessResponseJSON(w, resp)
}

// Celery 格式
type celeryParams struct {
	TaskType       int    `json:"task_type"`
	SourceFileURL  string `json:"source_file_url"`
	SourceFileName string `json:"source_file_name"`
	TargetFileType int    `json:"target_file_type"`
	TargetFileURL  string `json:"target_file_url"`
	celeryMeta     `json:"meta"`
}

type celeryMeta struct {
	CreateAt *int64  `json:"create_at"`
	Etag     *string `json:"etag,omitempty"`
}

const transformTaskType = 5

// 格式转换服务有效source type
var transformValidFromType = map[string]struct{}{
	"docx": struct{}{},
	"doc":  struct{}{},
}

var transformValidType = map[string]int{
	"pdf": 4,
}

const celeryTaskName = "celery_app.process_task"
const celeryQueueName = "rag_data_process_tasks"

// ///////////  celery client /////////////
func newCeleryClient(endpoint string) (*gocelery.CeleryClient, error) {
	redisPool := &redis.Pool{
		MaxIdle:         5,                 // maximum number of idle connections in the pool
		MaxActive:       50,                // maximum number of connections allocated by the pool at a given time
		IdleTimeout:     600 * time.Second, // close connections after remaining idle for this duration
		Wait:            false,
		MaxConnLifetime: 7200 * time.Second,
		Dial: func() (redis.Conn, error) {
			c, err := redis.DialURL(fmt.Sprintf("redis://%s", endpoint))
			if err != nil {
				return nil, err
			}
			return c, err
		},
		TestOnBorrow: func(c redis.Conn, t time.Time) error {
			_, err := c.Do("PING")
			return err
		},
	}
	redisBroker := gocelery.NewRedisBroker(redisPool)
	redisBroker.QueueName = celeryQueueName

	// initialize celery client
	cli, err := gocelery.NewCeleryClient(
		redisBroker,
		&gocelery.RedisCeleryBackend{Pool: redisPool},
		1,
	)

	return cli, err
}

func (api customAPIHandlers) launchCeleryTask(param celeryParams) error {
	//console.Debugf("launch celery task param: %+v", param)
	if len(api.celeryEndpint) == 0 && api.celery == nil {
		return errors.New("not implement")
	}
	var err error
	if api.celery == nil {
		api.mtx.Lock()
		if api.celery == nil {
			api.celery, err = newCeleryClient(api.celeryEndpint)
		}
		api.mtx.Unlock()
		if api.celery == nil {
			return errors.New("no valid celery client")
		}
	}

	request, err := json.Marshal(param)
	if err != nil {
		return err
	}

	_, err = api.celery.Delay(celeryTaskName, string(request))
	if err != nil {
		return err
	}
	return nil
}
