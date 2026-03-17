/*
 *	api-router-customize-datalake.go 包含datalake自定义的service,
 *  这些业务接口和minio 本身(实际是 juicefs-gateway --> minio-gateway) 在同一个进程运行:
 *	1. files api: 用户侧直接使用的类似openai的文件处理接口
 */

package cmd

import (
	"bufio"
	"bytes"
	"crypto/aes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	pathUtils "path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gocelery/gocelery"
	"github.com/gorilla/mux"
	"github.com/minio/minio/cmd/config/dns"
	"github.com/minio/minio/cmd/crypto"
	xhttp "github.com/minio/minio/cmd/http"
	"github.com/minio/minio/cmd/logger"
	"github.com/minio/minio/pkg/bucket/lifecycle"
	"github.com/minio/minio/pkg/bucket/replication"
	"github.com/minio/minio/pkg/console"
	"github.com/minio/minio/pkg/event"
	"github.com/minio/minio/pkg/handlers"
	"github.com/minio/minio/pkg/hash"
	iampolicy "github.com/minio/minio/pkg/iam/policy"
	"github.com/minio/minio/pkg/mimedb"
	xnet "github.com/minio/minio/pkg/net"
)

const (
	datalakePath              = "/v1/"
	datalakeBrowserAPI        = "/browser/checkalive"
	datalakeUploadFileAPI     = "/files"
	datalakeGetFileContentAPI = "/files/{file_id}/content"
	datalakeGetFileAPI        = "/files/{file_id}"
	datalakeListFilesAPI      = "/files"
	datalakeDeleteFileAPI     = "/files/{file_id}"

	datalakeTransformAPI = "/transform"
)

var (
	globalCustomizedDatalakeBucket = "myjfs"
	// 开启统一前缀文件名
	globalCustomizedDatalakPrefixOn = true
	globalCustomizedDatalakPrefix   = "lazyshared"

	globalCustomizedDatalakeBufferSize           = 1024 * 1024
	globalCustomizedDatalakePurposeRag           = "rag"
	globalCustomizedDatalakePurposeFinetune      = "fine-tune"
	globalCustomizedDatalakePurposeChat          = "chat"
	globalCustomizedDatalakePurposeAIReview      = "aireview"
	globalCustomizedDatalakePurposeAIWrite       = "aiwrite"
	globalCustomizedDatalakePurposeAIPPT         = "aippt"
	globalCustomizedDatalakePurposeAIGenerated   = "aigenerated"
	globalCustomizedDatalakePurposeRagCompatible = "rag_"
	globalCustomizedDatalakeIDSalt               = "13fde8ef8a9eaadfcaa06613e79d33bd"
)

// customAPIHandlers implements and provides http handlers for datalake API.
type customAPIHandlers struct {
	objectAPI func() ObjectLayer

	// juicefs gateway使用的minio gateway和minio cache没关系，直接走juicefs的fs system缓存
	// CacheAPI  func() CacheObjectLayer

	celery        *gocelery.CeleryClient
	celeryEndpint string
	mtx           sync.Mutex
}

// registerDatalakeRouter - registers datalake APIs.
func registerDatalakeRouter(router *mux.Router) {
	// 使用 datalake files server一定需要下层实现了object layer
	api := customAPIHandlers{
		objectAPI: newObjectLayerFn,
	}

	// 失败则静默
	if len(globalCLIContext.CeleryWorkerEndpoint) > 0 {
		cli, err := newCeleryClient(globalCLIContext.CeleryWorkerEndpoint)
		if err != nil {
			console.Errorf("new celery client failed, err: %v, endpoint: %s", err, globalCLIContext.CeleryWorkerEndpoint)
		}
		api.celery = cli
		api.celeryEndpint = globalCLIContext.CeleryWorkerEndpoint
	}

	// API Router
	apiRouter := router.PathPrefix(datalakePath).Subrouter()
	// checkalive for browser
	apiRouter.Methods(http.MethodGet).Path(datalakeBrowserAPI).HandlerFunc(
		httpTraceAll(api.CheckAliveHandler))
	apiRouter.Methods(http.MethodPost).Path(datalakeUploadFileAPI).HandlerFunc(
		httpTraceAll(api.UploadFileHandler))
	apiRouter.Methods(http.MethodGet).Path(datalakeGetFileContentAPI).HandlerFunc(
		httpTraceAll(api.GetFileContentHandler))
	apiRouter.Methods(http.MethodGet).Path(datalakeGetFileAPI).HandlerFunc(
		httpTraceAll(api.GetFileHandler))
	apiRouter.Methods(http.MethodDelete).Path(datalakeDeleteFileAPI).HandlerFunc(
		httpTraceAll(api.DeleteFileHandler))
	apiRouter.Methods(http.MethodGet).Path(datalakeListFilesAPI).HandlerFunc(
		httpTraceAll(api.ListFilesHandler))

	// transform API
	apiRouter.Methods(http.MethodPost).Path(datalakeTransformAPI).HandlerFunc(
		httpTraceAll(api.TransformFileHandler))
}

func (api customAPIHandlers) CheckAliveHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("CheckAliveHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "CheckAlive")
	if getRequestAuthType(r) != authTypeAnonymous {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrInvalidQueryParams), r.URL)
		return
	}

	resp, _ = json.Marshal(struct {
		Data string `json:"data"`
	}{
		Data: "Alive!",
	})
	writeSuccessResponseJSON(w, resp)
}

// UploadFileHandler 实际使用的是object.PutObject
// PubObject 建议最大使用5GB
func (api customAPIHandlers) UploadFileHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("UploadFileHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "UploadFile")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	if err := r.ParseMultipartForm(100 << 20); err != nil {
		console.Errorf("form value invalid, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	formValue := ""
	for key, values := range r.Form {
		formValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("UploadFileHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, formValue)

	if getRequestAuthType(r) != authTypeDatalake {
		console.Errorf("invalid sensetime header, request_id: %s, type: %v", w.Header().Get(xhttp.AmzRequestID), getRequestAuthType(r))
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}
	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Upload cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	// 检验参数合法性
	purpose := r.FormValue("purpose")
	path := r.FormValue("path")
	bucket := globalCustomizedDatalakeBucket
	reader, readerHeader, err := r.FormFile("file")
	if err != nil {
		console.Errorf("get form-data file failed, request_id: %s, trace_id: %s, err: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	defer reader.Close()
	defer r.MultipartForm.RemoveAll()

	size := readerHeader.Size
	if size == -1 {
		console.Errorf("empty file, request_id: %s, trace_id: %s", w.Header().Get(xhttp.AmzRequestID), user.TraceID)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrMissingContentLength), r.URL)
		return
	}
	// 仅支持5GB以内的文件上传，较大时使用MultiPart接口
	if isMaxPutObjectSize(size) {
		console.Errorf("file size too large, request_id: %s, trace_id: %s, size: %d", w.Header().Get(xhttp.AmzRequestID), user.TraceID, size)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrEntityTooLarge), r.URL)
		return
	}
	// 如果无path参数，那么直接本地生成对应path，此时接口和OpenAi对齐
	if len(path) == 0 {
		path = standardObject(pathUtils.Join(purpose, readerHeader.Filename))
	}

	id, object, err := generateObjectName(path, purpose, user)
	if err != nil {
		console.Errorf("file params invalid, request_id: %s, trace_id: %s, path: %s, purpose: %s, user_id: %s, err: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, path, purpose, getUserPath(user), err)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	// 如果是minio standalone，必须去掉object slash prefix
	object = strings.TrimPrefix(object, "/")

	metadata, err := extractMetadata(ctx, r)
	if err != nil {
		console.Errorf("extract meta data failed, request_id: %s, trace_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), user.TraceID, err)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	t := time.Now().Unix()
	metadata[xhttp.AmzObjectTagging] = fmt.Sprintf("created_at=%d&file_id=%s", t, id)
	var (
		s3Err     APIErrorCode
		putObject = datalakeAPI.PutObject
	)
	if s3Err = isDatalakeActionAllowed(ctx, bucket, object, r, iampolicy.PutObjectAction); s3Err != ErrNone {
		console.Errorf("no put authorization, err: %v, request_id: %s, trace_id: %s, path: %d, purpose: %s, user_id: %s",
			s3Err, w.Header().Get(xhttp.AmzRequestID), user.TraceID, path, purpose, getUserPath(user))
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrUnauthorizedAccess), r.URL)
		return
	}

	hashReader, err := hash.NewReader(reader, size, "", "", size)
	if err != nil {
		console.Errorf("new reader failed, request_id: %s, trace_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), user.TraceID, err)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	rawReader := hashReader
	pReader := NewPutObjReader(rawReader)
	var opts ObjectOptions
	opts, err = putOpts(ctx, r, bucket, object, metadata)
	if err != nil {
		console.Errorf("get put object opts err, request_id: %s, trace_id: %s, err: %v, object: %s, metadata: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, metadata)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	// openai http 过来的请求自动屏蔽掉 S3保留期限和法律保留的功能
	// TODO: 注意S3 sdk过来的请求也需要禁用
	// openai http 过来的请求自动屏蔽掉 mustReplicate功能，不可读取复制规则，详情请见s3:GetReplicationConfiguration作用
	// 不支持服务端提供的 SSE-KMS，屏蔽自动加密功能，上层gateway不可开启 --encrypt功能

	// Ensure that metadata does not contain sensitive information
	crypto.RemoveSensitiveEntries(metadata)
	objInfo, err := putObject(ctx, bucket, object, pReader, opts)
	if err != nil {
		console.Errorf("put object err, request_id: %s, trace_id: %s, err: %v, object: %s, opts: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	// 过滤掉本身的复制规则鉴权，开启minio版本控制，注意这里因为实际使用的是minio gateway版本，因此不会走到副本复制
	// scheduleReplication 这里无需调用

	setPutObjHeaders(w, objInfo, false)
	// _, filename, _ := getFileMeta(path)
	respJ := fileObject{
		ID:       id,
		Len:      objInfo.Size,
		CreateAt: t,
		//Filename: filename,
		Filename: object,
		Purpose:  purpose,
	}
	rid := w.Header().Get(xhttp.AmzRequestID)
	if len(user.TraceID) > 0 {
		rid = user.TraceID
	}
	resp, err = json.Marshal(struct {
		RequestID string `json:"request_id"`
		fileObject
	}{
		RequestID:  rid,
		fileObject: respJ,
	})
	if err != nil {
		console.Errorf("marshal resp err, request_id: %s, trace_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), user.TraceID, err)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	writeSuccessResponseJSON(w, resp)

	// event机制还是需要使用的，juicefs 上层用到了事件通知
	go sendEvent(eventArgs{
		EventName:    event.ObjectCreatedPut,
		BucketName:   bucket,
		Object:       objInfo,
		ReqParams:    extractReqParams(r),
		RespElements: extractRespElements(w),
		UserAgent:    r.UserAgent(),
		Host:         handlers.GetSourceIP(r),
	})
}

func (api customAPIHandlers) GetFileContentHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	defer func() {
		console.Debugf("GetFileContentHandler stats, request_id: %s, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "GetFileContent")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	vars := mux.Vars(r)
	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	value := ""
	for key, values := range vars {
		value += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("GetFileContentHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, value)

	if getRequestAuthType(r) != authTypeDatalake {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}
	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Upload cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	bucket := globalCustomizedDatalakeBucket
	id := vars["file_id"]
	file_id_pad, ok := vars["file_id_pad"]
	if ok {
		id = id + file_id_pad
	}
	object, err := getFileObjectName(id, user)
	if err != nil {
		console.Errorf("invalid file_id, request_id: %s, trace_id: %s, err: %v, file_id: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id)
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

	opts, err := getOpts(ctx, r, bucket, object)
	if err != nil {
		console.Errorf("get object opts err, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	getObjectNInfo := datalakeAPI.GetObjectNInfo
	gr, err := getObjectNInfo(ctx, bucket, object, nil, r.Header, readLock, opts)
	if err != nil {
		console.Errorf("get object err, request_id: %s, trace_id: %s, err: %v, object: %s, ops: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		// 目录同样会报错
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrNoSuchKey), r.URL)
		return
	}
	defer gr.Close()

	objInfo := gr.ObjInfo
	if objInfo.IsDir {
		console.Errorf("try to download a dict, request_id: %s, trace_id: %s, err: %v, object: %s, ops: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrNoSuchKey), r.URL)
		return
	}
	filetype := strings.TrimPrefix(ext(object), ".")
	mime, ok := mimedb.DB[filetype]
	if ok {
		objInfo.ContentType = mime.ContentType
	} else {
		objInfo.ContentType = "application/octet-stream"
	}

	// 不调用 globalLifecycleSys.Get(bucket)，不去查看生命周期，JFSGateway自动屏蔽该功能
	var rs *HTTPRangeSpec
	if err = setObjectHeaders(w, objInfo, rs, opts); err != nil {
		console.Errorf("set object err, request_id: %s, trace_id: %s, err: %v, object: %s, opts: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	setHeadGetRespHeaders(w, r.URL.Query())

	writer := bufio.NewWriterSize(w, globalCustomizedDatalakeBufferSize)
	bufferedReader := bufio.NewReaderSize(gr, globalCustomizedDatalakeBufferSize)

	// Write object content to response body
	if _, err = io.Copy(writer, bufferedReader); err != nil {
		// write error response only if no data or headers has been written to client yet
		console.Infof("Unable to write data to client, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, toAPIError(ctx, err), r.URL)
		if !xnet.IsNetworkOrHostDown(err, true) { // do not need to log disconnected clients
			console.Infof("Unable to write all the data to client, request_id: %s, trace_id: %s, err: %v, object: %s",
				w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		}
		return
	}

	if err = writer.Flush(); err != nil {
		console.Infof("Unable to flush data to client, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		writeSuccessResponseJSON(w, nil)
		if !xnet.IsNetworkOrHostDown(err, true) { // do not need to log disconnected clients
			console.Infof("Unable to flush all the data to client, request_id: %s, trace_id: %s, err: %v, object: %s",
				w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		}
		return
	}

	writeSuccessResponseJSON(w, nil)

	// event机制还是需要使用的，juicefs 上层用到了事件通知
	go sendEvent(eventArgs{
		EventName:    event.ObjectAccessedGet,
		BucketName:   bucket,
		Object:       objInfo,
		ReqParams:    extractReqParams(r),
		RespElements: extractRespElements(w),
		UserAgent:    r.UserAgent(),
		Host:         handlers.GetSourceIP(r),
	})
}

// 使用的是ListObjectV2
// 当prefix为空时，和openai接口对齐
func (api customAPIHandlers) ListFilesHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("ListFilesHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "ListObjectV2")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	query := r.URL.Query()
	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	value := ""
	for key, values := range query {
		value += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("ListFilesHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, value)

	if getRequestAuthType(r) != authTypeDatalake {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}
	var err error
	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Upload cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	bucket := globalCustomizedDatalakeBucket
	limitStr := query.Get("limit")
	if len(limitStr) == 0 {
		limitStr = "100"
	}
	limit, _ := strconv.ParseInt(limitStr, 10, 64)
	purpose := query.Get("purpose")
	afterID := query.Get("after")
	// delimiter 只支持slash
	delimiter := query.Get("delimiter")
	if len(delimiter) != 0 && delimiter != "/" {
		console.Errorf("list prefix delimiter invalid, request_id: %s, trace_id: %s, err: %v, delimiter: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, delimiter)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	prefix := query.Get("prefix")
	prefix, err = getListPrefix(purpose, prefix, user)
	if err != nil {
		console.Errorf("list prefix invalid, request_id: %s, trace_id: %s, err: %v, purpose: %s, prefix: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, purpose, prefix)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	var after string
	if len(afterID) > 0 {
		after, err = getFileObjectName(afterID, user)
		if err != nil {
			console.Errorf("calculate object name err when list, request_id: %s, trace_id: %s, err: %v, file_id: %s, user_id: %s",
				w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, after, getUserPath(user))
			customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
			return
		}
	}
	listObjectsV2 := datalakeAPI.ListObjectsV2
	// Gateway 的fetchOwner没有使用，false or true都可
	listObjectsV2Info, err := listObjectsV2(ctx, bucket, prefix, "", delimiter, int(limit), true, after)
	if err != nil {
		console.Errorf("list object err, request_id: %s, trace_id: %s, err: %v, prefix: %s, limit: %d, after: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, prefix, limit, after)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	resData := []fileObject{}
	// 当前路径下文件展示
	for _, obj := range listObjectsV2Info.Objects {
		// purpose, filename := extractFileMetas(obj.Name, user)
		purpose, _ := extractFileMetas(obj.Name, user)
		id, _, err := calculateFilePath(obj.Name)
		if err != nil {
			console.Errorf("calculateFilePath err, request_id: %s, trace_id: %s, err: %v, object: %s, user_id: %s",
				w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, obj.Name, getUserPath(user))
			customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
			return
		}

		mdata, _ := parseQuery(obj.UserTags)
		createdTime, _ := strconv.ParseInt(mdata["created_at"], 10, 64)
		var expireT int64
		if !obj.Expires.IsZero() {
			expireT = obj.Expires.Unix()
		}
		resData = append(resData, fileObject{
			ID:  id,
			Len: obj.Size,
			// Filename: filename,
			Filename: obj.Name,
			CreateAt: createdTime,
			ExpireAt: expireT,
			Purpose:  purpose,
		})
	}
	// 当前路径下文件夹展示
	if delimiter == "/" {
		for _, prefix := range listObjectsV2Info.Prefixes {
			id, _, err := calculateFilePath(prefix)
			if err != nil {
				console.Errorf("calculateFilePath dir err, request_id: %s, trace_id: %s, err: %v, prefix: %s, user_id: %s",
					w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, prefix, getUserPath(user))
				customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
				return
			}
			dirname := strings.TrimPrefix(prefix, "/")
			if !strings.HasSuffix(dirname, "/") {
				dirname += "/"
			}
			resData = append(resData, fileObject{
				ID:       id,
				Filename: dirname,
				Purpose:  purpose,
			})
		}
	}
	rid := w.Header().Get(xhttp.AmzRequestID)
	if len(user.TraceID) > 0 {
		rid = user.TraceID
	}
	res := struct {
		Data      []fileObject `json:"data"`
		RequestID string       `json:"request_id"`
	}{
		Data:      resData,
		RequestID: rid,
	}
	resp, err = json.Marshal(res)
	if err != nil {
		console.Errorf("marshal err, request_id: %s, trace_id: %s, err: %v, res: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, res)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	writeSuccessResponseJSON(w, resp)
}

func (api customAPIHandlers) GetFileHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("GetFileHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "HeadObject")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	vars := mux.Vars(r)
	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	value := ""
	for key, values := range vars {
		value += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("GetFileHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, value)

	if getRequestAuthType(r) != authTypeDatalake {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Upload cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	bucket := globalCustomizedDatalakeBucket
	id := vars["file_id"]
	file_id_pad, ok := vars["file_id_pad"]
	if ok {
		id = id + file_id_pad
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
	var rs *HTTPRangeSpec
	if err = setObjectHeaders(w, objInfo, rs, opts); err != nil {
		console.Errorf("set object err, request_id: %s, trace_id: %s, err: %v, object: %s, opts: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}

	setHeadGetRespHeaders(w, r.URL.Query())

	mdata, _ := parseQuery(objInfo.UserTags)
	createdTime, _ := strconv.ParseInt(mdata["created_at"], 10, 64)
	// purpose, filename := extractFileMetas(object, user)
	purpose, _ := extractFileMetas(object, user)
	var expireT int64
	if !objInfo.Expires.IsZero() {
		expireT = objInfo.Expires.Unix()
	}
	respJ := fileObject{
		ID:       id,
		Len:      objInfo.Size,
		CreateAt: createdTime,
		ExpireAt: expireT,
		// Filename: filename,
		Filename: objInfo.Name,
		Purpose:  purpose,
	}
	rid := w.Header().Get(xhttp.AmzRequestID)
	if len(user.TraceID) > 0 {
		rid = user.TraceID
	}
	resp, err = json.Marshal(struct {
		RequestID string `json:"request_id"`
		fileObject
	}{
		RequestID:  rid,
		fileObject: respJ,
	})
	if err != nil {
		console.Errorf("marshal get err, request_id: %s, trace_id: %s, err: %v, res: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, respJ)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	writeSuccessResponseJSON(w, resp)

	go sendEvent(eventArgs{
		EventName:    event.ObjectAccessedHead,
		BucketName:   bucket,
		Object:       objInfo,
		ReqParams:    extractReqParams(r),
		RespElements: extractRespElements(w),
		UserAgent:    r.UserAgent(),
		Host:         handlers.GetSourceIP(r),
	})
}

func (api customAPIHandlers) DeleteFileHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var resp []byte
	defer func() {
		console.Debugf("DeleteFileHandler stats, request_id: %s, response: %v, start: %d, cost: %dms",
			w.Header().Get(xhttp.AmzRequestID), string(resp), start.UnixMilli(), time.Since(start).Milliseconds())
	}()

	ctx := newContext(r, w, "DeleteObject")
	defer logger.AuditLog(ctx, w, r, mustGetClaimsFromToken(r))

	datalakeAPI := api.objectAPI()
	if datalakeAPI == nil {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrNotImplemented), r.URL)
		return
	}

	vars := mux.Vars(r)
	headerValue := ""
	for key, values := range r.Header {
		headerValue += fmt.Sprintf("  [%s = %v]", key, values)
	}
	value := ""
	for key, values := range vars {
		value += fmt.Sprintf("  [%s = %v]", key, values)
	}
	console.Debugf("DeleteFileHandler get request, request_id: %s, header: %v, values: %v",
		w.Header().Get(xhttp.AmzRequestID), headerValue, value)

	if getRequestAuthType(r) != authTypeDatalake {
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	user, err := getUserInfo(r)
	if err != nil {
		console.Errorf("Upload cannot get user header, request_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), err)
		writeErrorResponseJSON(ctx, w, errorCodes.ToAPIErr(ErrAuthHeaderEmpty), r.URL)
		return
	}

	bucket := globalCustomizedDatalakeBucket
	id := vars["file_id"]
	object, err := getFileObjectName(id, user)
	if err != nil {
		console.Errorf("invalid delete file_id, request_id: %s, trace_id: %s, err: %v, file_id: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, id)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInvalidRequestParameter), r.URL)
		return
	}
	// 操作者是否有操作权限
	if err := isDatalakeActionAllowed(ctx, bucket, object, r, iampolicy.DeleteObjectAction); err != ErrNone {
		console.Errorf("no delete authorization, err: %v, request_id: %s, trace_id: %s, object: %s, user_id: %s",
			err, w.Header().Get(xhttp.AmzRequestID), user.TraceID, object, getUserPath(user))
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrUnauthorizedAccess), r.URL)
		return
	}

	getObjectInfo := datalakeAPI.GetObjectInfo
	if globalDNSConfig != nil {
		_, err := globalDNSConfig.Get(bucket)
		if err != nil && err != dns.ErrNotImplemented {
			console.Errorf("globalDNS cannot access bucket, request_id: %s, trace_id: %s, err: %v", w.Header().Get(xhttp.AmzRequestID), user.TraceID, err)
			customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
			return
		}
	}

	opts, err := delOpts(ctx, r, bucket, object)
	if err != nil {
		console.Errorf("delOpts err, request_id: %s, trace_id: %s, err: %v, object: %s",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	var (
		hasLockEnabled, hasLifecycleConfig bool
		goi                                ObjectInfo
		gerr                               error
	)
	replicateDeletes := hasReplicationRules(ctx, bucket, []ObjectToDelete{{ObjectName: object, VersionID: opts.VersionID}})
	if rcfg, _ := globalBucketObjectLockSys.Get(bucket); rcfg.LockEnabled {
		hasLockEnabled = true
	}
	if _, err := globalBucketMetadataSys.GetLifecycleConfig(bucket); err == nil {
		hasLifecycleConfig = true
	}
	if replicateDeletes || hasLockEnabled || hasLifecycleConfig {
		goi, gerr = getObjectInfo(ctx, bucket, object, ObjectOptions{
			VersionID: opts.VersionID,
		})
	}

	replicateDel, replicateSync := checkReplicateDelete(ctx, bucket, ObjectToDelete{ObjectName: object, VersionID: opts.VersionID}, goi, gerr)
	if replicateDel {
		if opts.VersionID != "" {
			opts.VersionPurgeStatus = Pending
		} else {
			opts.DeleteMarkerReplicationStatus = string(replication.Pending)
		}
	}

	vID := opts.VersionID
	apiErr := ErrNone
	if rcfg, _ := globalBucketObjectLockSys.Get(bucket); rcfg.LockEnabled {
		if vID != "" {
			apiErr = enforceRetentionBypassForDelete(ctx, r, bucket, ObjectToDelete{
				ObjectName: object,
				VersionID:  vID,
			}, goi, gerr)
			if apiErr != ErrNone && apiErr != ErrNoSuchKey {
				console.Errorf("get invalid versionID, request_id: %s, trace_id: %s, err: %v, object: %s, vID: %s",
					w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, vID)
				customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
				return
			}
		}
	}

	rid := w.Header().Get(xhttp.AmzRequestID)
	if len(user.TraceID) > 0 {
		rid = user.TraceID
	}
	resp, _ = json.Marshal(struct {
		ID        string `json:"id"`
		Deleted   bool   `json:"deleted"`
		RequestID string `json:"request_id"`
	}{
		ID:        id,
		RequestID: rid,
	})
	if apiErr == ErrNoSuchKey {
		writeSuccessResponseJSON(w, resp)
		return
	}

	deleteObject := datalakeAPI.DeleteObject
	objInfo, err := deleteObject(ctx, bucket, object, opts)
	if err != nil {
		console.Errorf("delete object err, request_id: %s, trace_id: %s, err: %v, object: %s, opts: %v",
			w.Header().Get(xhttp.AmzRequestID), user.TraceID, err, object, opts)
		customizeDatalakeWriteErrorResponseJSON(ctx, w, r, errorCodes.ToAPIErr(ErrInternalError), r.URL)
		return
	}
	if objInfo.Name == "" {
		writeSuccessResponseJSON(w, resp)
		return
	}

	resp, _ = json.Marshal(struct {
		ID        string `json:"id"`
		Deleted   bool   `json:"deleted"`
		RequestID string `json:"request_id"`
	}{
		ID:        id,
		Deleted:   true,
		RequestID: rid,
	})
	setPutObjHeaders(w, objInfo, true)
	writeSuccessResponseJSON(w, resp)

	eventName := event.ObjectRemovedDelete
	if objInfo.DeleteMarker {
		eventName = event.ObjectRemovedDeleteMarkerCreated
	}

	// Notify object deleted event.
	go sendEvent(eventArgs{
		EventName:    eventName,
		BucketName:   bucket,
		Object:       objInfo,
		ReqParams:    extractReqParams(r),
		RespElements: extractRespElements(w),
		UserAgent:    r.UserAgent(),
		Host:         handlers.GetSourceIP(r),
	})

	if replicateDel {
		dmVersionID := ""
		versionID := ""
		if objInfo.DeleteMarker {
			dmVersionID = objInfo.VersionID
		} else {
			versionID = objInfo.VersionID
		}
		dobj := DeletedObjectVersionInfo{
			DeletedObject: DeletedObject{
				ObjectName:                    object,
				VersionID:                     versionID,
				DeleteMarkerVersionID:         dmVersionID,
				DeleteMarkerReplicationStatus: string(objInfo.ReplicationStatus),
				DeleteMarkerMTime:             DeleteMarkerMTime{objInfo.ModTime},
				DeleteMarker:                  objInfo.DeleteMarker,
				VersionPurgeStatus:            objInfo.VersionPurgeStatus,
			},
			Bucket: bucket,
		}
		go scheduleReplicationDelete(ctx, dobj, datalakeAPI, replicateSync)
	}

	if goi.TransitionStatus == lifecycle.TransitionComplete { // clean up transitioned tier
		go deleteTransitionedObject(ctx, datalakeAPI, bucket, object, lifecycle.ObjectOpts{
			Name:             object,
			UserTags:         goi.UserTags,
			VersionID:        goi.VersionID,
			DeleteMarker:     goi.DeleteMarker,
			TransitionStatus: goi.TransitionStatus,
			IsLatest:         goi.IsLatest,
		}, false, true)
	}
}

func isMaxPutObjectSize(size int64) bool {
	return size > globalMaxPartSize
}

// 用户自定义header
type userInfo struct {
	UserID   string
	UserName string
	IsPlain  bool // 是否支持header同名时扁平化path
	TraceID  string
}

// 用户自定义header获取逻辑
func getUserInfo(r *http.Request) (userInfo, error) {
	var u userInfo

	// 优先看是否使用oneapi头
	if len(r.Header.Get(xhttp.SensetimeOneAPIUserID)) > 0 &&
		len(r.Header.Get(xhttp.SensetimeOneAPIUserName)) > 0 {
		u.UserID = r.Header.Get(xhttp.SensetimeOneAPIUserID)
		u.UserName = r.Header.Get(xhttp.SensetimeOneAPIUserName)
		u.IsPlain = true
		return u, nil
	}

	if len(r.Header.Get(xhttp.SensetimeSaaSTraceID)) > 0 {
		u.TraceID = r.Header.Get(xhttp.SensetimeSaaSTraceID)
	}
	if len(r.Header.Get(xhttp.SensetimeSaaSUserID)) > 0 &&
		len(r.Header.Get(xhttp.SensetimeSaaSTenantID)) > 0 {
		u.UserID = r.Header.Get(xhttp.SensetimeSaaSUserID)
		u.UserName = r.Header.Get(xhttp.SensetimeSaaSTenantID)
		return u, nil
	}

	return u, errors.New("invalid user params")
}

type fileObject struct {
	ID       string `json:"id"`
	Len      int64  `json:"bytes"`
	CreateAt int64  `json:"created_at"`
	ExpireAt int64  `json:"expires_at"`
	Filename string `json:"filename"`
	Purpose  string `json:"purpose"`
}

func standardObject(object ...string) string {
	joined := pathUtils.Join(object...)
	return pathUtils.Join("/", joined)
}

// //////////// PATH LOGIC BEGIN /////////////
var validPurposeMap = map[string]interface{}{
	globalCustomizedDatalakePurposeRag:           struct{}{},
	globalCustomizedDatalakePurposeFinetune:      struct{}{},
	globalCustomizedDatalakePurposeChat:          struct{}{},
	globalCustomizedDatalakePurposeAIReview:      struct{}{},
	globalCustomizedDatalakePurposeAIWrite:       struct{}{},
	globalCustomizedDatalakePurposeAIPPT:         struct{}{},
	globalCustomizedDatalakePurposeAIGenerated:   struct{}{},
	globalCustomizedDatalakePurposeRagCompatible: struct{}{},
}

var fileTypeRag = map[string]interface{}{
	".json":  struct{}{},
	".jsonl": struct{}{},
	".pdf":   struct{}{},
	".docx":  struct{}{},
	".html":  struct{}{},
	".md":    struct{}{},
	".pptx":  struct{}{},
	".csv":   struct{}{},
	".xls":   struct{}{},
}

var fileTypeFinetune = map[string]interface{}{
	".json":  struct{}{},
	".jsonl": struct{}{},
}

func isValidPath(path string, prefixes map[string]interface{}, withName bool) bool {
	if !strings.HasPrefix(path, "/") {
		return false
	}
	if strings.Contains(path, "//") {
		return false
	}
	cleaned := filepath.Clean(path)
	if cleaned != path {
		return false
	}

	var keys []string
	for prefix := range prefixes {
		keys = append(keys, prefix)
	}
	prefixPattern := strings.Join(keys, "|")
	if !withName {
		regexPattern := fmt.Sprintf(`^/(%s)(/[^/]+)*$`, prefixPattern)
		regex := regexp.MustCompile(regexPattern)

		return regex.MatchString(path)
	}
	regexPattern := fmt.Sprintf(`^/[\w\-.]+/(%s)(/[^/]+)*$`, prefixPattern)
	regex := regexp.MustCompile(regexPattern)

	return regex.MatchString(path)
}

func ext(path string) string {
	for i := len(path) - 1; i >= 0 && path[i] != '/'; i-- {
		if path[i] == '.' {
			return path[i:]
		}
	}
	return ""
}

// path 需要形如 /rag/prefix/filename.type /rag/filename.type
func getFileMeta(path string) (purpose string, filename string, valid bool) {
	prefix := strings.Split(path, "/")
	if len(prefix) <= 2 {
		valid = false
		return
	}
	purpose = prefix[1]
	/*
		fileType := ext(path)
		var typeMapping map[string]interface{}
		switch purpose {
		case globalCustomizedDatalakePurposeRag:
			typeMapping = fileTypeRag
		case globalCustomizedDatalakePurposeFinetune:
			typeMapping = fileTypeFinetune
		default:
			valid = false
			return
		}
		_, ok := typeMapping[fileType]
		if !ok {
			valid = false
			return
		}
	*/

	filename = prefix[len(prefix)-1]
	valid = true
	return
}

func pkcS7Padding(data []byte, blockSize int) []byte {
	padding := blockSize - len(data)%blockSize
	padText := bytes.Repeat([]byte{byte(padding)}, padding)
	return append(data, padText...)
}

func pkcS7Unpadding(data []byte) ([]byte, error) {
	length := len(data)
	if length == 0 {
		return nil, fmt.Errorf("invalid padding size")
	}
	padSize := int(data[length-1])
	if padSize > length {
		return nil, fmt.Errorf("invalid padding size")
	}
	return data[:length-padSize], nil
}

func encryptAES(plainText, key []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}

	blockSize := block.BlockSize()
	plainText = pkcS7Padding(plainText, blockSize)

	cipherText := make([]byte, len(plainText))

	for bs, be := 0, blockSize; bs < len(plainText); bs, be = bs+blockSize, be+blockSize {
		block.Encrypt(cipherText[bs:be], plainText[bs:be])
	}
	return cipherText, nil
}

func decryptAES(cipherText, key []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}

	blockSize := block.BlockSize()
	if len(cipherText)%blockSize != 0 {
		return nil, fmt.Errorf("cipherText is not a multiple of the block size")
	}

	plainText := make([]byte, len(cipherText))
	for bs, be := 0, blockSize; bs < len(cipherText); bs, be = bs+blockSize, be+blockSize {
		block.Decrypt(plainText[bs:be], cipherText[bs:be])
	}

	return pkcS7Unpadding(plainText)
}

// Base62 字符表
const base62Charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

func base62Encode(data []byte) string {
	num := new(big.Int).SetBytes(data) // 转换为大整数
	base := big.NewInt(62)
	encoded := ""

	for num.Cmp(big.NewInt(0)) > 0 {
		remainder := new(big.Int)
		num.DivMod(num, base, remainder)
		encoded = string(base62Charset[remainder.Int64()]) + encoded
	}

	return encoded
}

func base62Decode(encoded string) ([]byte, error) {
	base := big.NewInt(62)
	num := big.NewInt(0)

	for _, char := range encoded {
		index := strings.IndexRune(base62Charset, char)
		if index == -1 {
			return nil, fmt.Errorf("Invalid Base62 character found, str: %s", encoded)
		}
		num.Mul(num, base)
		num.Add(num, big.NewInt(int64(index)))
	}

	return num.Bytes(), nil
}

// 所有path遵循 object/path 格式而不是 /object/path
func calculateFilePath(inputPath string) (id string, object string, err error) {
	realPath := strings.TrimPrefix(inputPath, "/")
	// fileID通过realPath加密生成，这样在查找的时候解密可以直接得到path，并能计算出具体的object
	rawID, err := encryptAES([]byte(realPath), []byte(globalCustomizedDatalakeIDSalt))
	if err != nil {
		return
	}
	id = base62Encode(rawID)
	object = realPath
	return
}

// generateObjectName 用于UploadFile时生成存储名称
func generateObjectName(path, purpose string, user userInfo) (string, string, error) {
	// 检验path purpose和user 是否合法
	if len(path) == 0 {
		return "", "", errors.New("empty path name")
	}
	if _, ok := validPurposeMap[purpose]; !ok {
		return "", "", errors.New("invalid purpose name")
	}
	if ok := isValidPath(path, validPurposeMap, false); !ok {
		return "", "", errors.New("invalid path")
	}
	realPurpose, _, valid := getFileMeta(path)
	if !valid {
		return "", "", errors.New("invalid filename")
	}
	if realPurpose != purpose {
		return "", "", errors.New("invalid path")
	}

	path = strings.TrimPrefix(path, "/")
	if !strings.HasPrefix(path, user.UserName) {
		userpath := getUserPath(user)
		path = pathUtils.Join(userpath, path)
	}

	// 当开启全局前缀时，在所有的object name前增加 prefix
	if globalCustomizedDatalakPrefixOn {
		path = pathUtils.Join(globalCustomizedDatalakPrefix, path)
	}

	return calculateFilePath(path)
}

func getFileObjectName(id string, user userInfo) (string, error) {
	rawID, err := base62Decode(id)
	if err != nil {
		return "", err
	}
	object, err := decryptAES(rawID, []byte(globalCustomizedDatalakeIDSalt))
	if err != nil {
		return "", err
	}

	filePath := strings.TrimPrefix(string(object), "/")
	if globalCustomizedDatalakPrefixOn {
		filePath = strings.TrimPrefix(filePath, globalCustomizedDatalakPrefix)
	}
	userpath := getUserPath(user)
	if !strings.HasPrefix(standardObject(filePath), standardObject(userpath)) {
		return "", fmt.Errorf("no auth to access, name: %s, want: %s", userpath, filePath)
	}
	return string(object), nil
}

func extractFileMetas(object string, user userInfo) (purpose string, filename string) {
	path := object
	if globalCustomizedDatalakPrefixOn {
		path = strings.TrimPrefix(path, globalCustomizedDatalakPrefix)
	}
	path = standardObject(path)
	userpath := getUserPath(user)
	outputPath := strings.TrimPrefix(path, standardObject(userpath))
	path = standardObject(outputPath)
	purpose, filename, _ = getFileMeta(path)
	return
}

// list前缀需要手动去除其中有的slash前缀
func getListPrefix(purpose, prefix string, user userInfo) (string, error) {
	if _, ok := validPurposeMap[purpose]; !ok {
		return "", errors.New("invalid purpose name")
	}

	userpath := getUserPath(user)

	// 前缀为空，和openai接口对齐，拼接user_id和purpose
	if len(prefix) == 0 {
		if globalCustomizedDatalakPrefixOn {
			return pathUtils.Join(globalCustomizedDatalakPrefix, userpath, purpose) + "/", nil
		}
		return pathUtils.Join(userpath, purpose) + "/", nil
	}
	if !strings.HasPrefix(standardObject(userpath, prefix), standardObject(userpath, purpose)) {
		return "", errors.New("invalid prefix")
	}

	if globalCustomizedDatalakPrefixOn {
		return pathUtils.Join(globalCustomizedDatalakPrefix, userpath, prefix), nil
	}

	return pathUtils.Join(userpath, prefix), nil
}

// //////////// PATH LOGIC END /////////////

func parseQuery(raw string) (map[string]string, error) {
	m := make(map[string]string)

	values, err := url.ParseQuery(raw)
	if err != nil {
		return nil, err
	}
	for k, v := range values {
		if len(v) > 0 {
			m[k] = v[0]
		}
	}
	return m, nil
}

func getUserPath(user userInfo) string {
	if user.UserID == user.UserName && user.IsPlain {
		return user.UserID
	}

	return pathUtils.Join(user.UserName, user.UserID)
}
