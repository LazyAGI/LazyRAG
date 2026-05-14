package chat

import (
	"context"
	"strings"

	"gorm.io/gorm"
)

type selectedRuntimeModel struct {
	ModelType    string
	ProviderName string
	ModelName    string
	BaseURL      string
	APIKey       string
}

func loadLLMConfig(ctx context.Context, db *gorm.DB, userID string) (map[string]any, error) {
	var rows []selectedRuntimeModel
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

	return buildLLMConfig(rows), nil
}

func buildLLMConfig(rows []selectedRuntimeModel) map[string]any {
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
	if _, ok := out["evo_llm"]; !ok {
		if cfg, ok := out["llm"]; ok {
			out["evo_llm"] = cfg
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}
