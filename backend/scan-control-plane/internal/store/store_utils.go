package store

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gorm.io/gorm"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

func sourceID() string {
	return fmt.Sprintf("src_%d", time.Now().UnixNano())
}

func manualPullJobID() string {
	return fmt.Sprintf("mpj_%d", time.Now().UnixNano())
}

func cloudSyncRunID() string {
	return fmt.Sprintf("csr_%d", time.Now().UnixNano())
}

func normalizeReconcilePolicy(reconcileSeconds int64, reconcileSchedule string, fallbackSeconds int64) (int64, string, error) {
	schedule := strings.TrimSpace(reconcileSchedule)
	if schedule == "" {
		if reconcileSeconds <= 0 {
			reconcileSeconds = fallbackSeconds
		}
		return reconcileSeconds, "", nil
	}
	if _, _, _, err := parseReconcileScheduleExpr(schedule); err != nil {
		return 0, "", err
	}
	if reconcileSeconds <= 0 {
		reconcileSeconds = fallbackSeconds
	}
	return reconcileSeconds, schedule, nil
}

func parseReconcileScheduleExpr(expr string) (everyDays int, hour int, minute int, err error) {
	raw := strings.TrimSpace(expr)
	if raw == "" {
		return 0, 0, 0, fmt.Errorf("reconcile_schedule is empty")
	}
	lower := strings.ToLower(raw)
	if strings.HasPrefix(lower, "daily@") {
		h, m, perr := parseHourMinuteToken(raw[len("daily@"):])
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return 1, h, m, nil
	}
	if strings.HasPrefix(lower, "every") && strings.Contains(lower, "d@") {
		pos := strings.Index(lower, "d@")
		dayToken := strings.TrimSpace(raw[len("every"):pos])
		days, derr := strconv.Atoi(dayToken)
		if derr != nil || days <= 0 {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: invalid everyNd day token", expr)
		}
		h, m, perr := parseHourMinuteToken(raw[pos+2:])
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return days, h, m, nil
	}
	if strings.HasPrefix(raw, "每天") {
		h, m, perr := parseHourMinuteToken(strings.TrimSpace(strings.TrimPrefix(raw, "每天")))
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return 1, h, m, nil
	}
	if strings.HasPrefix(raw, "每") && strings.Contains(raw, "天") {
		pos := strings.Index(raw, "天")
		dayToken := strings.TrimSpace(raw[len("每"):pos])
		timeToken := strings.TrimSpace(raw[pos+len("天"):])
		days, derr := parseDayToken(dayToken)
		if derr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, derr)
		}
		h, m, perr := parseHourMinuteToken(timeToken)
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return days, h, m, nil
	}
	return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule format: %q", expr)
}

func parseHourMinuteToken(token string) (int, int, error) {
	value := strings.TrimSpace(token)
	if value == "" {
		return 0, 0, fmt.Errorf("time token is empty")
	}
	value = strings.ReplaceAll(value, "：", ":")
	if strings.Contains(value, ":") {
		parts := strings.Split(value, ":")
		if len(parts) != 2 {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		h, errH := strconv.Atoi(strings.TrimSpace(parts[0]))
		m, errM := strconv.Atoi(strings.TrimSpace(parts[1]))
		if errH != nil || errM != nil {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	value = strings.ReplaceAll(value, "时", "点")
	if strings.Contains(value, "点") {
		parts := strings.SplitN(value, "点", 2)
		if len(parts) != 2 {
			return 0, 0, fmt.Errorf("invalid 点 format")
		}
		h, err := strconv.Atoi(strings.TrimSpace(parts[0]))
		if err != nil {
			return 0, 0, fmt.Errorf("invalid hour")
		}
		minuteRaw := strings.TrimSpace(parts[1])
		minuteRaw = strings.TrimSuffix(minuteRaw, "分")
		m := 0
		if strings.TrimSpace(minuteRaw) != "" {
			mv, err := strconv.Atoi(strings.TrimSpace(minuteRaw))
			if err != nil {
				return 0, 0, fmt.Errorf("invalid minute")
			}
			m = mv
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	// Fallback: only hour token.
	h, err := strconv.Atoi(value)
	if err != nil {
		return 0, 0, fmt.Errorf("invalid hour")
	}
	if h < 0 || h > 23 {
		return 0, 0, fmt.Errorf("hour out of range")
	}
	return h, 0, nil
}

func parseDayToken(token string) (int, error) {
	raw := strings.TrimSpace(token)
	if raw == "" {
		return 0, fmt.Errorf("empty day token")
	}
	if v, err := strconv.Atoi(raw); err == nil && v > 0 {
		return v, nil
	}
	parsed := parseChineseNumber(raw)
	if parsed <= 0 {
		return 0, fmt.Errorf("invalid day token")
	}
	return parsed, nil
}

func parseChineseNumber(raw string) int {
	s := strings.TrimSpace(raw)
	if s == "" {
		return 0
	}
	digit := map[string]int{
		"零": 0,
		"一": 1,
		"二": 2,
		"两": 2,
		"三": 3,
		"四": 4,
		"五": 5,
		"六": 6,
		"七": 7,
		"八": 8,
		"九": 9,
	}
	if v, ok := digit[s]; ok {
		return v
	}
	if strings.Contains(s, "十") {
		parts := strings.SplitN(s, "十", 2)
		tens := 1
		if strings.TrimSpace(parts[0]) != "" {
			v, ok := digit[strings.TrimSpace(parts[0])]
			if !ok {
				return 0
			}
			tens = v
		}
		ones := 0
		if len(parts) > 1 && strings.TrimSpace(parts[1]) != "" {
			v, ok := digit[strings.TrimSpace(parts[1])]
			if !ok {
				return 0
			}
			ones = v
		}
		return tens*10 + ones
	}
	return 0
}

func normalizePatterns(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func encodeJSON(v any) string {
	data, err := json.Marshal(v)
	if err != nil {
		return ""
	}
	return string(data)
}

func decodeStringSliceJSON(raw string) []string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return []string{}
	}
	var out []string
	if err := json.Unmarshal([]byte(value), &out); err != nil {
		return []string{}
	}
	return normalizePatterns(out)
}

func decodeMapJSON(raw string) map[string]any {
	value := strings.TrimSpace(raw)
	if value == "" {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(value), &out); err != nil || out == nil {
		return map[string]any{}
	}
	return out
}

func (s *Store) computeNextSyncAt(scheduleExpr, scheduleTZ string, nowUTC time.Time) *time.Time {
	expr := strings.TrimSpace(scheduleExpr)
	if expr == "" {
		return nil
	}
	everyDays, hour, minute, err := parseReconcileScheduleExpr(expr)
	if err != nil {
		return nil
	}
	if everyDays <= 0 {
		everyDays = 1
	}
	tz := strings.TrimSpace(scheduleTZ)
	if tz == "" {
		tz = strings.TrimSpace(s.defaultScheduleTZ)
		if tz == "" {
			tz = defaultScheduleTZ
		}
	}
	loc, err := time.LoadLocation(tz)
	if err != nil {
		loc = time.UTC
	}
	localNow := nowUTC.In(loc)
	next := time.Date(localNow.Year(), localNow.Month(), localNow.Day(), hour, minute, 0, 0, loc)
	for !next.After(localNow) {
		next = next.AddDate(0, 0, everyDays)
	}
	nextUTC := next.UTC()
	return &nextUTC
}

func (s *Store) EnsureSourceByRootPath(ctx context.Context, req model.CreateSourceRequest) (model.Source, error) {
	return s.ensureSourceByRootPath(ctx, req)
}

func normalizePathsUnderRoot(paths []string, root string) ([]string, int) {
	cleanRoot := filepath.Clean(strings.TrimSpace(root))
	if cleanRoot == "" || cleanRoot == "." {
		return nil, len(paths)
	}
	unique := make(map[string]struct{}, len(paths))
	out := make([]string, 0, len(paths))
	skipped := 0
	for _, raw := range paths {
		p := filepath.Clean(strings.TrimSpace(raw))
		if p == "" || p == "." {
			skipped++
			continue
		}
		if p != cleanRoot && !strings.HasPrefix(p, cleanRoot+string(filepath.Separator)) {
			skipped++
			continue
		}
		if _, ok := unique[p]; ok {
			continue
		}
		unique[p] = struct{}{}
		out = append(out, p)
	}
	return out, skipped
}

func normalizeEventType(v string) string {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "created":
		return "created"
	case "deleted":
		return "deleted"
	default:
		return "modified"
	}
}

func firstNonEmpty(values ...string) string {
	for _, item := range values {
		if strings.TrimSpace(item) != "" {
			return strings.TrimSpace(item)
		}
	}
	return ""
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func isUniqueConstraintError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "duplicate key") ||
		strings.Contains(msg, "unique constraint") ||
		strings.Contains(msg, "is not unique")
}

func (s *Store) applyParseTaskFilters(db *gorm.DB, filter parseTaskFilter) *gorm.DB {
	if filter.TenantID != "" {
		db = db.Where("pt.tenant_id = ?", filter.TenantID)
	}
	if filter.SourceID != "" {
		db = db.Where("d.source_id = ?", filter.SourceID)
	}
	if len(filter.Statuses) > 0 {
		db = db.Where("pt.status IN ?", filter.Statuses)
	}
	keyword := strings.TrimSpace(filter.Keyword)
	if keyword != "" {
		pattern := "%" + keyword + "%"
		if s.db.Dialector.Name() == "postgres" {
			db = db.Where("d.source_object_id ILIKE ?", pattern)
		} else {
			db = db.Where("LOWER(d.source_object_id) LIKE ?", strings.ToLower(pattern))
		}
	}
	return db
}

func buildParseTaskFilter(req model.ListParseTasksRequest) parseTaskFilter {
	return parseTaskFilter{
		TenantID: strings.TrimSpace(req.TenantID),
		SourceID: strings.TrimSpace(req.SourceID),
		Statuses: splitCSV(req.Status),
		Keyword:  strings.TrimSpace(req.Keyword),
	}
}

func splitCSV(v string) []string {
	raw := strings.TrimSpace(v)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	uniq := make(map[string]struct{}, len(parts))
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		item := strings.TrimSpace(p)
		if item == "" {
			continue
		}
		if _, ok := uniq[item]; ok {
			continue
		}
		uniq[item] = struct{}{}
		out = append(out, item)
	}
	return out
}

func normalizePageAndSize(page, pageSize int) (int, int) {
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}
	if pageSize > 200 {
		pageSize = 200
	}
	return page, pageSize
}

func normalizeUpdateTypeFilter(raw string) string {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "NEW":
		return "NEW"
	case "MODIFIED":
		return "MODIFIED"
	case "DELETED":
		return "DELETED"
	case "NONE", "UNCHANGED":
		return "UNCHANGED"
	default:
		return ""
	}
}

func applyUpdateTypeFilter(db *gorm.DB, updateType string) *gorm.DB {
	switch updateType {
	case "NEW":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND (current_version_id IS NULL OR current_version_id = '')", "DELETED")
	case "MODIFIED":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND current_version_id IS NOT NULL AND current_version_id <> '' AND desired_version_id <> current_version_id", "DELETED")
	case "DELETED":
		return db.Where("parse_status = ?", "DELETED")
	case "UNCHANGED":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND desired_version_id = current_version_id", "DELETED")
	default:
		return db
	}
}
