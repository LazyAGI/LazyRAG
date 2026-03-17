package doc

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	corestore "lazyrag/core/store"

	"github.com/gorilla/mux"
)

// DatasetService 占位实现，后续补全。

// ----- API 数据结构：严格对齐 ragservice_Dataset表结构与DatasetService接口.md -----

type Algo struct {
	AlgoID      string `json:"algo_id"`
	Description string `json:"description"`
	DisplayName string `json:"display_name"`
}

type ParserConfig struct {
	Name   string         `json:"name"`
	Params map[string]any `json:"params"`
	Type   string         `json:"type"`
}

type Dataset struct {
	Name           string         `json:"name"`
	DatasetID      string         `json:"dataset_id"`
	DisplayName    string         `json:"display_name"`
	Desc           string         `json:"desc"`
	CoverImage     string         `json:"cover_image"`
	State          string         `json:"state"`
	IsEmpty        bool           `json:"is_empty"`
	DocumentCount  int64          `json:"document_count"`
	DocumentSize   int64          `json:"document_size"`
	SegmentCount   int64          `json:"segment_count"`
	TokenCount     int64          `json:"token_count"`
	Parsers        []ParserConfig `json:"parsers"`
	Algo           Algo           `json:"algo"`
	Creator        string         `json:"creator"`
	CreateTime     time.Time      `json:"create_time"`
	UpdateTime     time.Time      `json:"update_time"`
	Acl            []string       `json:"acl"`
	ShareType      string         `json:"share_type"`
	Type           string         `json:"type"`
	Tags           []string       `json:"tags"`
	DefaultDataset bool           `json:"default_dataset"`
	Industry       string         `json:"industry"`
}

type ListAlgosResponse struct {
	Algos []Algo `json:"algos"`
}

type AllDatasetTagsResponse struct {
	Tags []string `json:"tags"`
}

type ListDatasetsResponse struct {
	Datasets      []Dataset `json:"datasets"`
	TotalSize     int32     `json:"total_size"`
	NextPageToken string    `json:"next_page_token"`
}

type SetDefaultDatasetRequest struct {
	Name string `json:"name"`
}

type UnsetDefaultDatasetRequest struct {
	Name string `json:"name"`
}

type algoListResp struct {
	Code int    `json:"code"`
	Msg  string `json:"msg"`
	Data []struct {
		AlgoID      string `json:"algo_id"`
		DisplayName string `json:"display_name"`
		Description string `json:"description"`
		CreatedAt   string `json:"created_at"`
		UpdatedAt   string `json:"updated_at"`
	} `json:"data"`
}

type extTags struct {
	Tags     []string `json:"tags"`
	AlgoID   string   `json:"algo_id"`
	AlgoName string   `json:"algo_name"`
}

func parseDatasetTags(ext json.RawMessage) []string {
	if len(ext) == 0 {
		return nil
	}
	var v extTags
	if err := json.Unmarshal(ext, &v); err != nil {
		return nil
	}
	out := make([]string, 0, len(v.Tags))
	seen := map[string]struct{}{}
	for _, t := range v.Tags {
		tt := strings.TrimSpace(t)
		if tt == "" {
			continue
		}
		if _, ok := seen[tt]; ok {
			continue
		}
		seen[tt] = struct{}{}
		out = append(out, tt)
	}
	return out
}

func parseDatasetAlgo(ext json.RawMessage) Algo {
	if len(ext) == 0 {
		return Algo{}
	}
	var v extTags
	if err := json.Unmarshal(ext, &v); err != nil {
		return Algo{}
	}
	return Algo{AlgoID: strings.TrimSpace(v.AlgoID), DisplayName: strings.TrimSpace(v.AlgoName)}
}

func datasetTypeToPB(t uint8) string {
	switch t {
	case 2:
		return "DATASET_TYPE_TABLE"
	case 3:
		return "DATASET_TYPE_GRAPH"
	default:
		return "DATASET_TYPE_TEXT"
	}
}

func datasetTypeFromPB(s string) uint8 {
	switch strings.TrimSpace(s) {
	case "DATASET_TYPE_TABLE":
		return 2
	case "DATASET_TYPE_GRAPH":
		return 3
	default:
		return 1
	}
}

func shareTypeToPB(_ uint8) string { return "SHARE_TYPE_UNSPECIFIED" }
func stateToPB(_ uint8) string     { return "STATE_UNSPECIFIED" }

func datasetIDFromPath(r *http.Request) string {
	raw := mux.Vars(r)["dataset"]
	raw = strings.TrimSpace(raw)
	raw = strings.TrimPrefix(raw, "datasets/")
	raw = strings.TrimPrefix(raw, "/")
	return raw
}

func ListAlgos(w http.ResponseWriter, r *http.Request) {
	// 该接口需要请求外部服务。
	const listAlgosPath = "/v1/algo/list"
	algoURL := common.JoinURL(common.AlgoServiceEndpoint(), listAlgosPath)

	var ar algoListResp
	if err := common.ApiGet(r.Context(), algoURL, nil, &ar, 5*time.Second); err != nil {
		common.ReplyErr(w, "algo service unavailable", http.StatusBadGateway)
		return
	}
	if ar.Code != 200 {
		common.ReplyErr(w, "algo service error: "+strings.TrimSpace(ar.Msg), http.StatusBadGateway)
		return
	}

	algos := make([]Algo, 0, len(ar.Data))
	for _, a := range ar.Data {
		algos = append(algos, Algo{AlgoID: a.AlgoID, DisplayName: a.DisplayName, Description: a.Description})
	}
	common.ReplyJSON(w, ListAlgosResponse{Algos: algos})
}
func AllDatasetTags(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	var datasets []orm.Dataset
	if err := corestore.DB().
		Select("ext").
		Where("create_user_id = ? AND deleted_at IS NULL", userID).
		Find(&datasets).Error; err != nil {
		common.ReplyErr(w, "query datasets failed", http.StatusInternalServerError)
		return
	}

	seen := map[string]struct{}{}
	var tags []string
	for _, ds := range datasets {
		for _, t := range parseDatasetTags(ds.Ext) {
			if _, ok := seen[t]; ok {
				continue
			}
			seen[t] = struct{}{}
			tags = append(tags, t)
		}
	}
	sort.Strings(tags)
	common.ReplyJSON(w, AllDatasetTagsResponse{Tags: tags})
}
func ListDatasets(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	q := r.URL.Query()
	pageToken := strings.TrimSpace(q.Get("page_token"))
	pageSizeStr := strings.TrimSpace(q.Get("page_size"))
	orderBy := strings.TrimSpace(q.Get("order_by"))
	keyword := strings.TrimSpace(q.Get("keyword"))
	rawTags := q["tags"]

	pageSize := 20
	if pageSizeStr != "" {
		if v, err := strconv.Atoi(pageSizeStr); err == nil && v > 0 {
			pageSize = v
		}
	}
	if pageSize > 100 {
		pageSize = 100
	}

	offset := 0
	if pageToken != "" {
		if v, err := strconv.Atoi(pageToken); err == nil && v >= 0 {
			offset = v
		}
	}

	// 解析 tags（query 可多次出现 tags=...，也可能是 tags=a,b）
	tagSet := map[string]struct{}{}
	var wantTags []string
	for _, rt := range rawTags {
		for _, part := range strings.Split(rt, ",") {
			t := strings.TrimSpace(part)
			if t == "" {
				continue
			}
			if _, ok := tagSet[t]; ok {
				continue
			}
			tagSet[t] = struct{}{}
			wantTags = append(wantTags, t)
		}
	}

	db := corestore.DB().Model(&orm.Dataset{}).
		Where("create_user_id = ? AND deleted_at IS NULL", userID)

	if keyword != "" {
		like := "%" + strings.ReplaceAll(keyword, "%", "\\%") + "%"
		db = db.Where("(display_name LIKE ? OR `desc` LIKE ?)", like, like)
	}

	// order_by: "create_time desc" / "update_time desc" / "display_name asc"
	if orderBy != "" {
		if ob, err := normalizeDatasetOrderBy(orderBy); err == nil {
			db = db.Order(ob)
		}
	} else {
		db = db.Order("updated_at desc")
	}

	// 若有 tags 过滤：先取较大的窗口在内存中过滤（简单实现，避免各 DB 的 JSON 语法差异）
	fetchLimit := pageSize
	if len(wantTags) > 0 {
		fetchLimit = 1000
		if fetchLimit < pageSize {
			fetchLimit = pageSize
		}
	}

	var rows []orm.Dataset
	if err := db.
		Select("id, display_name, `desc`, cover_image, created_at, updated_at, ext, type, share_type, dataset_state").
		Limit(fetchLimit).
		Offset(0).
		Find(&rows).Error; err != nil {
		common.ReplyErr(w, "query datasets failed", http.StatusInternalServerError)
		return
	}

	filtered := rows
	if len(wantTags) > 0 {
		filtered = filtered[:0]
		for _, ds := range rows {
			tags := parseDatasetTags(ds.Ext)
			if containsAll(tags, wantTags) {
				filtered = append(filtered, ds)
			}
		}
	}

	total := len(filtered)
	end := offset + pageSize
	if offset > total {
		offset = total
	}
	if end > total {
		end = total
	}
	page := filtered[offset:end]

	out := make([]Dataset, 0, len(page))
	for _, ds := range page {
		out = append(out, Dataset{
			Name:           "datasets/" + ds.ID,
			DatasetID:      ds.ID,
			DisplayName:    ds.DisplayName,
			Desc:           ds.Desc,
			CoverImage:     ds.CoverImage,
			State:          stateToPB(ds.DatasetState),
			IsEmpty:        false,
			DocumentCount:  0,
			DocumentSize:   0,
			SegmentCount:   0,
			TokenCount:     0,
			Parsers:        nil,
			Algo:           parseDatasetAlgo(ds.Ext),
			Creator:        "", // 未在查询字段中包含 create_user_name
			CreateTime:     ds.CreatedAt,
			UpdateTime:     ds.UpdatedAt,
			Acl:            nil,
			ShareType:      shareTypeToPB(ds.ShareType),
			Type:           datasetTypeToPB(ds.Type),
			Tags:           parseDatasetTags(ds.Ext),
			DefaultDataset: false,
			Industry:       "",
		})
	}

	nextToken := ""
	if end < total {
		nextToken = strconv.Itoa(end)
	}
	common.ReplyJSON(w, ListDatasetsResponse{
		Datasets:      out,
		TotalSize:     int32(total),
		NextPageToken: nextToken,
	})
}

func normalizeDatasetOrderBy(orderBy string) (string, error) {
	orderBy = strings.TrimSpace(orderBy)
	if orderBy == "" {
		return "", errors.New("empty")
	}
	parts := strings.Fields(orderBy)
	if len(parts) == 0 {
		return "", errors.New("empty")
	}
	field := parts[0]
	dir := "asc"
	if len(parts) > 1 {
		dir = strings.ToLower(parts[1])
	}
	if dir != "asc" && dir != "desc" {
		return "", errors.New("bad dir")
	}
	switch field {
	case "create_time", "created_at":
		return "created_at " + dir, nil
	case "update_time", "updated_at":
		return "updated_at " + dir, nil
	case "display_name":
		return "display_name " + dir, nil
	default:
		return "", errors.New("unsupported order_by")
	}
}

func containsAll(have []string, want []string) bool {
	if len(want) == 0 {
		return true
	}
	set := map[string]struct{}{}
	for _, h := range have {
		set[h] = struct{}{}
	}
	for _, w := range want {
		if _, ok := set[w]; !ok {
			return false
		}
	}
	return true
}

func newDatasetID() string {
	// 16 bytes -> 32 hex chars
	var b [16]byte
	_, _ = rand.Read(b[:])
	return fmt.Sprintf("ds_%x", b[:])
}

func isDefaultDatasetForUser(ctx context.Context, userID, datasetID string) bool {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(datasetID) == "" {
		return false
	}
	var n int64
	_ = corestore.DB().WithContext(ctx).
		Model(&orm.DefaultDataset{}).
		Where("create_user_id = ? AND dataset_id = ? AND deleted_at IS NULL", userID, datasetID).
		Count(&n).Error
	return n > 0
}

type kbCreateRequest struct {
	KbID           string                 `json:"kb_id"`
	DisplayName    *string                `json:"display_name,omitempty"`
	Description    *string                `json:"description,omitempty"`
	OwnerID        *string                `json:"owner_id,omitempty"`
	Meta           map[string]any         `json:"meta,omitempty"`
	AlgoID         string                 `json:"algo_id,omitempty"`
	IdempotencyKey *string                `json:"idempotency_key,omitempty"`
}

type kbUpdateRequest struct {
	DisplayName    *string        `json:"display_name,omitempty"`
	Description    *string        `json:"description,omitempty"`
	OwnerID        *string        `json:"owner_id,omitempty"`
	Meta           map[string]any `json:"meta,omitempty"`
	AlgoID         *string        `json:"algo_id,omitempty"`
	IdempotencyKey *string        `json:"idempotency_key,omitempty"`
}

func CreateDataset(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	userName := corestore.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	// query: dataset_id (optional)
	datasetID := strings.TrimSpace(r.URL.Query().Get("dataset_id"))
	if datasetID == "" {
		datasetID = newDatasetID()
	}

	var body Dataset
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.Type) == "" {
		common.ReplyErr(w, "type required", http.StatusBadRequest)
		return
	}

	displayName := strings.TrimSpace(body.DisplayName)
	desc := strings.TrimSpace(body.Desc)
	cover := strings.TrimSpace(body.CoverImage)
	if displayName == "" {
		displayName = datasetID
	}

	algoID := strings.TrimSpace(body.Algo.AlgoID)
	if algoID == "" {
		algoID = "__default__"
	}

	// 1) 调外部 POST /v1/kbs 创建 KB
	const createKBPath = "/v1/kbs"
	kbURL := common.JoinURL(common.KbServiceEndpoint(), createKBPath)

	req := kbCreateRequest{
		KbID:        datasetID,
		AlgoID:      algoID,
		Meta:        map[string]any{"tags": body.Tags},
	}
	// optional pointers (omit empty)
	if displayName != "" {
		req.DisplayName = &displayName
	}
	if desc != "" {
		req.Description = &desc
	}
	if userID != "" {
		req.OwnerID = &userID
	}

	if err := common.ApiPost(r.Context(), kbURL, req, nil, nil, 10*time.Second); err != nil {
		common.ReplyErr(w, "kb service create failed", http.StatusBadGateway)
		return
	}

	// 2) 本地落库 datasets（新增字段 kb_id）
	now := time.Now().UTC()
	extBytes, _ := json.Marshal(map[string]any{
		"tags": body.Tags,
		"algo_id": algoID,
		"algo_name": body.Algo.DisplayName,
	})

	ds := orm.Dataset{
		ID:    datasetID,
		KbID:  datasetID,
		DisplayName: displayName,
		Desc:        desc,
		CoverImage:  cover,

		// 下面字段在当前模型中为 not null，这里先用可用的默认值占位（后续可按 ragservice 逻辑补齐）。
		ResourceUID: datasetID,
		BucketName:  "",
		OssPath:     "",
		DatasetInfo: json.RawMessage(`{}`),
		DatasetState: 0,
		EmbeddingModel: "default",
		EmbeddingModelProvider: "default",
		ShareType: 0,
		TenantID:  "",
		IsDemonstrate: false,
		Type: datasetTypeFromPB(body.Type),
		Ext:  extBytes,
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}

	if err := corestore.DB().WithContext(context.Background()).Create(&ds).Error; err != nil {
		common.ReplyErr(w, "create dataset failed", http.StatusInternalServerError)
		return
	}

	common.ReplyJSON(w, Dataset{
		Name:           "datasets/" + ds.ID,
		DatasetID:      ds.ID,
		DisplayName:    ds.DisplayName,
		Desc:           ds.Desc,
		CoverImage:     ds.CoverImage,
		State:          "STATE_UNSPECIFIED",
		IsEmpty:        true,
		DocumentCount:  0,
		DocumentSize:   0,
		SegmentCount:   0,
		TokenCount:     0,
		Parsers:        nil,
		Algo:           Algo{AlgoID: algoID, DisplayName: body.Algo.DisplayName, Description: body.Algo.Description},
		Creator:        userName,
		CreateTime:     ds.CreatedAt,
		UpdateTime:     ds.UpdatedAt,
		Acl:            nil,
		ShareType:      "SHARE_TYPE_UNSPECIFIED",
		Type:           body.Type,
		Tags:           body.Tags,
		DefaultDataset: false,
		Industry:       body.Industry,
	})
}
func GetDataset(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "invalid dataset id", http.StatusBadRequest)
		return
	}

	var ds orm.Dataset
	if err := corestore.DB().
		Where("id = ? AND create_user_id = ? AND deleted_at IS NULL", datasetID, userID).
		First(&ds).Error; err != nil {
		common.ReplyErr(w, "dataset not found", http.StatusNotFound)
		return
	}

	common.ReplyJSON(w, Dataset{
		Name:           "datasets/" + ds.ID,
		DatasetID:      ds.ID,
		DisplayName:    ds.DisplayName,
		Desc:           ds.Desc,
		CoverImage:     ds.CoverImage,
		State:          stateToPB(ds.DatasetState),
		IsEmpty:        false,
		DocumentCount:  0,
		DocumentSize:   0,
		SegmentCount:   0,
		TokenCount:     0,
		Parsers:        nil,
		Algo:           parseDatasetAlgo(ds.Ext),
		Creator:        ds.CreateUserName,
		CreateTime:     ds.CreatedAt,
		UpdateTime:     ds.UpdatedAt,
		Acl:            nil,
		ShareType:      shareTypeToPB(ds.ShareType),
		Type:           datasetTypeToPB(ds.Type),
		Tags:           parseDatasetTags(ds.Ext),
		DefaultDataset: isDefaultDatasetForUser(r.Context(), userID, ds.ID),
		Industry:       "",
	})
}
func DeleteDataset(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "invalid dataset id", http.StatusBadRequest)
		return
	}

	var ds orm.Dataset
	if err := corestore.DB().
		Where("id = ? AND create_user_id = ? AND deleted_at IS NULL", datasetID, userID).
		First(&ds).Error; err != nil {
		common.ReplyErr(w, "dataset not found", http.StatusNotFound)
		return
	}

	// 1) 调外部 DELETE /v1/kbs/{kb_id}
	kbID := ds.KbID
	if strings.TrimSpace(kbID) == "" {
		kbID = ds.ID
	}
	kbURL := common.JoinURL(common.KbServiceEndpoint(), "/v1/kbs/"+kbID)
	_ = common.ApiDelete(r.Context(), kbURL, nil, nil, 10*time.Second)

	// 2) 本地软删 datasets
	now := time.Now().UTC()
	ds.DeletedAt = &now
	ds.UpdatedAt = now
	if err := corestore.DB().Save(&ds).Error; err != nil {
		common.ReplyErr(w, "delete dataset failed", http.StatusInternalServerError)
		return
	}

	// 3) 清理默认知识库记录
	_ = corestore.DB().
		Where("create_user_id = ? AND dataset_id = ?", userID, datasetID).
		Delete(&orm.DefaultDataset{}).Error

	w.WriteHeader(http.StatusOK)
}
func UpdateDataset(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	userName := corestore.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "invalid dataset id", http.StatusBadRequest)
		return
	}

	var body Dataset
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}

	var ds orm.Dataset
	if err := corestore.DB().
		Where("id = ? AND create_user_id = ? AND deleted_at IS NULL", datasetID, userID).
		First(&ds).Error; err != nil {
		common.ReplyErr(w, "dataset not found", http.StatusNotFound)
		return
	}

	newDisplay := strings.TrimSpace(body.DisplayName)
	newDesc := strings.TrimSpace(body.Desc)
	newCover := strings.TrimSpace(body.CoverImage)
	if newDisplay == "" {
		newDisplay = ds.DisplayName
	}
	if newDesc == "" {
		newDesc = ds.Desc
	}
	if newCover == "" {
		newCover = ds.CoverImage
	}

	// 更新 ext: tags / algo (保持现有 algo_id，允许通过 body.algo.algo_id 覆盖)
	algo := parseDatasetAlgo(ds.Ext)
	algoID := strings.TrimSpace(body.Algo.AlgoID)
	if algoID == "" {
		algoID = algo.AlgoID
	}
	algoName := strings.TrimSpace(body.Algo.DisplayName)
	if algoName == "" {
		algoName = algo.DisplayName
	}
	extBytes, _ := json.Marshal(map[string]any{
		"tags":      body.Tags,
		"algo_id":   algoID,
		"algo_name": algoName,
	})

	// 1) 调外部 POST /v1/kbs/{kb_id}/update
	kbID := ds.KbID
	if strings.TrimSpace(kbID) == "" {
		kbID = ds.ID
	}
	kbURL := common.JoinURL(common.KbServiceEndpoint(), "/v1/kbs/"+kbID+"/update")
	extMeta := map[string]any{"tags": body.Tags}
	req := kbUpdateRequest{
		DisplayName: &newDisplay,
		Description: &newDesc,
		OwnerID:     &userID,
		Meta:        extMeta,
	}
	if algoID != "" {
		req.AlgoID = &algoID
	}
	if err := common.ApiPost(r.Context(), kbURL, req, nil, nil, 10*time.Second); err != nil {
		common.ReplyErr(w, "kb service update failed", http.StatusBadGateway)
		return
	}

	now := time.Now().UTC()
	ds.DisplayName = newDisplay
	ds.Desc = newDesc
	ds.CoverImage = newCover
	ds.Ext = extBytes
	ds.UpdatedAt = now
	ds.CreateUserName = userName

	if err := corestore.DB().Save(&ds).Error; err != nil {
		common.ReplyErr(w, "update dataset failed", http.StatusInternalServerError)
		return
	}

	common.ReplyJSON(w, Dataset{
		Name:           "datasets/" + ds.ID,
		DatasetID:      ds.ID,
		DisplayName:    ds.DisplayName,
		Desc:           ds.Desc,
		CoverImage:     ds.CoverImage,
		State:          stateToPB(ds.DatasetState),
		IsEmpty:        false,
		DocumentCount:  0,
		DocumentSize:   0,
		SegmentCount:   0,
		TokenCount:     0,
		Parsers:        nil,
		Algo:           parseDatasetAlgo(ds.Ext),
		Creator:        ds.CreateUserName,
		CreateTime:     ds.CreatedAt,
		UpdateTime:     ds.UpdatedAt,
		Acl:            nil,
		ShareType:      shareTypeToPB(ds.ShareType),
		Type:           datasetTypeToPB(ds.Type),
		Tags:           parseDatasetTags(ds.Ext),
		DefaultDataset: isDefaultDatasetForUser(r.Context(), userID, ds.ID),
		Industry:       "",
	})
}
func SetDefault(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	userName := corestore.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "invalid dataset id", http.StatusBadRequest)
		return
	}
	var body SetDefaultDatasetRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.Name) == "" {
		common.ReplyErr(w, "name required", http.StatusBadRequest)
		return
	}

	// 保证 dataset 存在且属于该用户
	var ds orm.Dataset
	if err := corestore.DB().
		Where("id = ? AND create_user_id = ? AND deleted_at IS NULL", datasetID, userID).
		First(&ds).Error; err != nil {
		common.ReplyErr(w, "dataset not found", http.StatusNotFound)
		return
	}

	now := time.Now().UTC()
	row := orm.DefaultDataset{
		DatasetID:   datasetID,
		DatasetName: body.Name,
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	// upsert: delete old then insert (简化，避免不同 DB Upsert 语法差异)
	_ = corestore.DB().
		Where("create_user_id = ? AND dataset_id = ?", userID, datasetID).
		Delete(&orm.DefaultDataset{}).Error
	if err := corestore.DB().Create(&row).Error; err != nil {
		common.ReplyErr(w, "set default failed", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
}
func UnsetDefault(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "invalid dataset id", http.StatusBadRequest)
		return
	}
	var body UnsetDefaultDatasetRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.Name) == "" {
		common.ReplyErr(w, "name required", http.StatusBadRequest)
		return
	}

	if err := corestore.DB().
		Where("create_user_id = ? AND dataset_id = ?", userID, datasetID).
		Delete(&orm.DefaultDataset{}).Error; err != nil {
		common.ReplyErr(w, "unset default failed", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}
func AllDefaultDatasets(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func PresignUploadCoverImageURL(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func SearchDatasets(w http.ResponseWriter, r *http.Request) {
	common.ReplyJSON(w, map[string]any{}) /* TODO */
}
func CallbackTask(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) /* TODO */ }
