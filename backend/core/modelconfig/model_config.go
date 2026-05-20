package modelconfig

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"gorm.io/gorm"
)

type SelectedRuntimeModel struct {
	ModelType    string
	ProviderName string
	ModelName    string
	BaseURL      string
	APIKey       string
}

func LoadLLMConfig(ctx context.Context, db *gorm.DB, userID string) (map[string]any, error) {
	var rows []SelectedRuntimeModel
	err := db.WithContext(ctx).
		Table("user_selected_models usm").
		Select(
			"usm.model_type, "+
				"m.provider_name, "+
				"m.name AS model_name, "+
				"m.base_url, "+
				"g.api_key",
		).
		Joins(
			"JOIN user_model_provider_group_models m ON "+
				"m.id = usm.user_model_provider_group_model_id AND "+
				"m.create_user_id = usm.user_id AND "+
				"m.deleted_at IS NULL",
		).
		Joins(
			"JOIN user_model_provider_groups g ON "+
				"g.id = m.user_model_provider_group_id AND "+
				"g.create_user_id = usm.user_id AND "+
				"g.deleted_at IS NULL",
		).
		Where("usm.user_id = ?", strings.TrimSpace(userID)).
		Scan(&rows).Error
	if err != nil {
		return nil, err
	}

	config := BuildLLMConfig(rows)
	fmt.Printf("[Core] [LLM_CONFIG_LOADED] [user_id=%s] [%s]\n", strings.TrimSpace(userID), SummarizeLLMConfigForLog(config))
	return config, nil
}

func BuildLLMConfig(rows []SelectedRuntimeModel) map[string]any {
	out := map[string]any{}
	for _, row := range rows {
		cfg := map[string]any{
			"source":   strings.ToLower(strings.TrimSpace(row.ProviderName)),
			"model":    row.ModelName,
			"base_url": row.BaseURL,
			"api_key":  row.APIKey,
		}
		switch strings.ToLower(strings.TrimSpace(row.ModelType)) {
		case "llm", "llm-chat":
			out["llm"] = cfg
		case "llm-evo", "llm2":
			out["evo_llm"] = cfg
		case "embedding", "embed":
			out["embed_main"] = cfg
		case "rerank", "reranker":
			out["reranker"] = cfg
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func SummarizeLLMConfigForLog(config map[string]any) string {
	if len(config) == 0 {
		return "roles=[]"
	}
	roles := make([]string, 0, len(config))
	for role := range config {
		roles = append(roles, role)
	}
	sort.Strings(roles)

	parts := make([]string, 0, len(roles)+1)
	parts = append(parts, "roles=["+strings.Join(roles, ",")+"]")
	for _, role := range roles {
		roleConfig, _ := config[role].(map[string]any)
		if roleConfig == nil {
			parts = append(parts, fmt.Sprintf("%s(type=%T)", role, config[role]))
			continue
		}
		parts = append(parts, fmt.Sprintf(
			"%s(source=%s, model=%s, base_url=%s, api_key=%s)",
			role,
			stringValue(roleConfig["source"]),
			stringValue(roleConfig["model"]),
			stringValue(roleConfig["base_url"]),
			APIKeyState(roleConfig["api_key"]),
		))
	}
	return strings.Join(parts, " ")
}

func stringValue(value any) string {
	s, _ := value.(string)
	return s
}

func APIKeyState(value any) string {
	if strings.TrimSpace(stringValue(value)) == "" {
		return "empty"
	}
	return "set"
}
