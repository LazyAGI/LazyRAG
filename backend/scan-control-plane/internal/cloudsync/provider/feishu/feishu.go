package feishu

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/lazyrag/scan_control_plane/internal/cloudsync/provider"
)

const apiBase = "https://open.feishu.cn/open-apis"

type Provider struct {
	baseURL string
	client  *http.Client
}

func New(timeout time.Duration) *Provider {
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	return &Provider{
		baseURL: apiBase,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

func (p *Provider) Name() string { return "feishu" }

func (p *Provider) ListObjects(ctx context.Context, req provider.ListRequest) ([]provider.RemoteObject, error) {
	accessToken := strings.TrimSpace(req.AccessToken)
	if accessToken == "" {
		return nil, fmt.Errorf("feishu access_token is empty")
	}
	targetType := strings.ToLower(strings.TrimSpace(req.TargetType))
	targetRef := strings.TrimSpace(req.TargetRef)
	switch targetType {
	case "wiki_space", "wiki":
		if targetRef == "" {
			targetRef = strings.TrimSpace(stringOption(req.ProviderOptions, "space_id"))
		}
		if targetRef == "" {
			return nil, fmt.Errorf("feishu wiki target_ref(space_id) is required")
		}
		return p.listWikiSpace(ctx, accessToken, targetRef)
	case "drive_folder", "folder":
		if targetRef == "" {
			targetRef = strings.TrimSpace(stringOption(req.ProviderOptions, "folder_token"))
		}
		return p.listDrive(ctx, accessToken, targetRef)
	default:
		// default to drive root for backward compatibility
		return p.listDrive(ctx, accessToken, targetRef)
	}
}

func (p *Provider) DownloadObject(ctx context.Context, accessToken string, object provider.RemoteObject) ([]byte, error) {
	accessToken = strings.TrimSpace(accessToken)
	if accessToken == "" {
		return nil, fmt.Errorf("feishu access_token is empty")
	}
	ref := strings.TrimSpace(object.DownloadRef)
	if ref == "" {
		ref = strings.TrimSpace(object.ExternalObjectID)
	}
	if ref == "" {
		return nil, fmt.Errorf("feishu object download ref is empty")
	}

	objType := strings.ToLower(strings.TrimSpace(stringOption(object.ProviderMeta, "obj_type")))
	kind := strings.ToLower(strings.TrimSpace(object.ExternalKind))
	switch {
	case objType == "docx" || kind == "docx":
		return p.downloadDocRaw(ctx, accessToken, ref, true)
	case objType == "doc" || kind == "doc":
		return p.downloadDocRaw(ctx, accessToken, ref, false)
	default:
		return p.downloadDriveFile(ctx, accessToken, ref)
	}
}

func (p *Provider) listDrive(ctx context.Context, accessToken, rootFolderToken string) ([]provider.RemoteObject, error) {
	visited := make(map[string]struct{}, 64)
	out := make([]provider.RemoteObject, 0, 512)
	if err := p.walkDriveFolder(ctx, accessToken, strings.TrimSpace(rootFolderToken), "", "", visited, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (p *Provider) walkDriveFolder(
	ctx context.Context,
	accessToken, folderToken, parentPath, parentID string,
	visited map[string]struct{},
	out *[]provider.RemoteObject,
) error {
	tokenKey := strings.TrimSpace(folderToken)
	if tokenKey != "" {
		if _, ok := visited[tokenKey]; ok {
			return nil
		}
		visited[tokenKey] = struct{}{}
	}

	items, err := p.listDriveFiles(ctx, accessToken, folderToken)
	if err != nil {
		return err
	}
	for _, item := range items {
		name := strings.TrimSpace(valueAsString(item["name"]))
		if name == "" {
			name = strings.TrimSpace(valueAsString(item["token"]))
		}
		token := strings.TrimSpace(valueAsString(item["token"]))
		if token == "" {
			continue
		}
		rawType := strings.TrimSpace(valueAsString(item["type"]))
		if rawType == "" {
			rawType = strings.TrimSpace(valueAsString(item["file_type"]))
		}
		currentPath := joinPath(parentPath, name)
		mod := parseFeishuTime(valueAsString(item["modified_time"]))
		if mod == nil {
			mod = parseFeishuTime(valueAsString(item["edit_time"]))
		}
		version := firstNonEmptyString(
			valueAsString(item["revision"]),
			valueAsString(item["modified_time"]),
			valueAsString(item["edit_time"]),
		)
		size := valueAsInt64(item["size"])
		isDir := strings.EqualFold(rawType, "folder")
		rec := provider.RemoteObject{
			ExternalObjectID:   token,
			ExternalParentID:   strings.TrimSpace(parentID),
			ExternalPath:       currentPath,
			ExternalName:       name,
			ExternalKind:       firstNonEmptyString(strings.ToLower(rawType), "file"),
			ExternalVersion:    version,
			ExternalModifiedAt: mod,
			SizeBytes:          size,
			DownloadRef:        token,
			ProviderMeta: map[string]any{
				"type": rawType,
			},
		}
		*out = append(*out, rec)
		if isDir {
			if err := p.walkDriveFolder(ctx, accessToken, token, currentPath, token, visited, out); err != nil {
				return err
			}
		}
	}
	return nil
}

func (p *Provider) listDriveFiles(ctx context.Context, accessToken, folderToken string) ([]map[string]any, error) {
	params := map[string]string{}
	if strings.TrimSpace(folderToken) != "" {
		params["folder_token"] = strings.TrimSpace(folderToken)
		params["page_size"] = "200"
	}

	out := make([]map[string]any, 0, 128)
	pageToken := ""
	for {
		if pageToken != "" {
			params["page_token"] = pageToken
		}
		var data struct {
			Files         []map[string]any `json:"files"`
			NextPageToken string           `json:"next_page_token"`
			PageToken     string           `json:"page_token"`
		}
		if err := p.getJSON(ctx, accessToken, "/drive/v1/files", params, &data); err != nil {
			return nil, err
		}
		out = append(out, data.Files...)
		if strings.TrimSpace(folderToken) == "" {
			// Root listing does not paginate.
			break
		}
		pageToken = strings.TrimSpace(firstNonEmptyString(data.NextPageToken, data.PageToken))
		if pageToken == "" {
			break
		}
	}
	return out, nil
}

func (p *Provider) listWikiSpace(ctx context.Context, accessToken, spaceID string) ([]provider.RemoteObject, error) {
	visited := make(map[string]struct{}, 128)
	out := make([]provider.RemoteObject, 0, 512)
	if err := p.walkWikiNodes(ctx, accessToken, spaceID, "", "", "", visited, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (p *Provider) walkWikiNodes(
	ctx context.Context,
	accessToken, spaceID, parentToken, parentPath, parentID string,
	visited map[string]struct{},
	out *[]provider.RemoteObject,
) error {
	pageToken := ""
	for {
		params := map[string]string{"page_size": "50"}
		if strings.TrimSpace(parentToken) != "" {
			params["parent_node_token"] = strings.TrimSpace(parentToken)
		}
		if pageToken != "" {
			params["page_token"] = pageToken
		}
		var data struct {
			Items         []map[string]any `json:"items"`
			Nodes         []map[string]any `json:"nodes"`
			PageToken     string           `json:"page_token"`
			NextPageToken string           `json:"next_page_token"`
		}
		if err := p.getJSON(ctx, accessToken, "/wiki/v2/spaces/"+url.PathEscape(spaceID)+"/nodes", params, &data); err != nil {
			return err
		}
		nodes := data.Items
		if len(nodes) == 0 {
			nodes = data.Nodes
		}
		for _, node := range nodes {
			nodeToken := strings.TrimSpace(firstNonEmptyString(valueAsString(node["node_token"]), valueAsString(node["token"])))
			if nodeToken == "" {
				continue
			}
			if _, ok := visited[nodeToken]; ok {
				continue
			}
			visited[nodeToken] = struct{}{}

			title := strings.TrimSpace(firstNonEmptyString(valueAsString(node["title"]), valueAsString(node["obj_name"]), nodeToken))
			objType := strings.ToLower(strings.TrimSpace(valueAsString(node["obj_type"])))
			objToken := strings.TrimSpace(valueAsString(node["obj_token"]))
			hasChild := valueAsBool(node["has_child"])
			isDir := hasChild || objType == "folder" || objType == "wiki" || objType == "space"
			currentPath := joinPath(parentPath, title)

			mod := parseFeishuTime(valueAsString(node["update_time"]))
			if mod == nil {
				mod = parseFeishuTime(valueAsString(node["edit_time"]))
			}
			if mod == nil {
				mod = parseFeishuTime(valueAsString(node["modified_time"]))
			}
			version := firstNonEmptyString(
				valueAsString(node["update_time"]),
				valueAsString(node["edit_time"]),
				valueAsString(node["modified_time"]),
			)
			downloadRef := objToken
			if downloadRef == "" {
				downloadRef = nodeToken
			}
			kind := objType
			if kind == "" {
				if isDir {
					kind = "folder"
				} else {
					kind = "file"
				}
			}
			rec := provider.RemoteObject{
				ExternalObjectID:   nodeToken,
				ExternalParentID:   strings.TrimSpace(parentID),
				ExternalPath:       currentPath,
				ExternalName:       title,
				ExternalKind:       kind,
				ExternalVersion:    version,
				ExternalModifiedAt: mod,
				SizeBytes:          valueAsInt64(node["size"]),
				DownloadRef:        downloadRef,
				ProviderMeta: map[string]any{
					"obj_type":   objType,
					"obj_token":  objToken,
					"node_token": nodeToken,
				},
			}
			*out = append(*out, rec)
			if isDir {
				if err := p.walkWikiNodes(ctx, accessToken, spaceID, nodeToken, currentPath, nodeToken, visited, out); err != nil {
					return err
				}
			}
		}
		pageToken = strings.TrimSpace(firstNonEmptyString(data.PageToken, data.NextPageToken))
		if pageToken == "" {
			break
		}
	}
	return nil
}

func (p *Provider) downloadDocRaw(ctx context.Context, accessToken, docToken string, isDocx bool) ([]byte, error) {
	pathSuffix := "/doc/v2/" + url.PathEscape(docToken) + "/raw_content"
	if isDocx {
		pathSuffix = "/docx/v1/documents/" + url.PathEscape(docToken) + "/raw_content"
	}
	var data struct {
		Content string `json:"content"`
	}
	if err := p.getJSON(ctx, accessToken, pathSuffix, nil, &data); err != nil {
		return nil, err
	}
	return []byte(data.Content), nil
}

func (p *Provider) downloadDriveFile(ctx context.Context, accessToken, fileToken string) ([]byte, error) {
	endpoint := p.baseURL + "/drive/v1/files/" + url.PathEscape(fileToken) + "/download"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+accessToken)
	resp, err := p.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("feishu file download returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if strings.Contains(strings.ToLower(resp.Header.Get("Content-Type")), "application/json") {
		var envelope struct {
			Code int    `json:"code"`
			Msg  string `json:"msg"`
		}
		if err := json.Unmarshal(body, &envelope); err == nil && envelope.Code != 0 {
			return nil, fmt.Errorf("feishu file download failed: %s (code=%d)", strings.TrimSpace(envelope.Msg), envelope.Code)
		}
	}
	return body, nil
}

func (p *Provider) getJSON(ctx context.Context, accessToken, apiPath string, params map[string]string, out any) error {
	endpoint := p.baseURL + apiPath
	u, err := url.Parse(endpoint)
	if err != nil {
		return err
	}
	query := u.Query()
	for k, v := range params {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		query.Set(k, v)
	}
	u.RawQuery = query.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("Content-Type", "application/json; charset=utf-8")

	resp, err := p.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("feishu api %s returned %d: %s", apiPath, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var envelope struct {
		Code int             `json:"code"`
		Msg  string          `json:"msg"`
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return fmt.Errorf("decode feishu api %s response failed: %w", apiPath, err)
	}
	if envelope.Code != 0 {
		return fmt.Errorf("feishu api %s failed: %s (code=%d)", apiPath, strings.TrimSpace(envelope.Msg), envelope.Code)
	}
	if out == nil {
		return nil
	}
	if len(envelope.Data) == 0 {
		return nil
	}
	if err := json.Unmarshal(envelope.Data, out); err != nil {
		return fmt.Errorf("decode feishu api %s data failed: %w", apiPath, err)
	}
	return nil
}

func joinPath(parent, name string) string {
	parent = strings.Trim(strings.TrimSpace(parent), "/")
	name = strings.Trim(strings.TrimSpace(name), "/")
	switch {
	case parent == "" && name == "":
		return ""
	case parent == "":
		return name
	case name == "":
		return parent
	default:
		return path.Clean(parent + "/" + name)
	}
}

func parseFeishuTime(raw string) *time.Time {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	if ts, err := strconv.ParseInt(raw, 10, 64); err == nil {
		if ts > 1e12 {
			t := time.UnixMilli(ts).UTC()
			return &t
		}
		t := time.Unix(ts, 0).UTC()
		return &t
	}
	if t, err := time.Parse(time.RFC3339, raw); err == nil {
		v := t.UTC()
		return &v
	}
	return nil
}

func valueAsString(v any) string {
	switch x := v.(type) {
	case nil:
		return ""
	case string:
		return strings.TrimSpace(x)
	case json.Number:
		return x.String()
	case float64:
		return strconv.FormatInt(int64(x), 10)
	case int64:
		return strconv.FormatInt(x, 10)
	case int:
		return strconv.Itoa(x)
	default:
		return strings.TrimSpace(fmt.Sprintf("%v", v))
	}
}

func valueAsInt64(v any) int64 {
	switch x := v.(type) {
	case nil:
		return 0
	case int64:
		return x
	case int:
		return int64(x)
	case float64:
		return int64(x)
	case json.Number:
		n, _ := x.Int64()
		return n
	case string:
		n, _ := strconv.ParseInt(strings.TrimSpace(x), 10, 64)
		return n
	default:
		s := strings.TrimSpace(fmt.Sprintf("%v", v))
		n, _ := strconv.ParseInt(s, 10, 64)
		return n
	}
}

func valueAsBool(v any) bool {
	switch x := v.(type) {
	case bool:
		return x
	case string:
		x = strings.TrimSpace(strings.ToLower(x))
		return x == "true" || x == "1" || x == "yes"
	case float64:
		return x != 0
	case int:
		return x != 0
	case int64:
		return x != 0
	default:
		return false
	}
}

func firstNonEmptyString(values ...string) string {
	for _, item := range values {
		if strings.TrimSpace(item) != "" {
			return strings.TrimSpace(item)
		}
	}
	return ""
}

func stringOption(options map[string]any, key string) string {
	if len(options) == 0 {
		return ""
	}
	return valueAsString(options[key])
}
