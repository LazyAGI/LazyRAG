package evolution

import (
	"context"
	"errors"
	"strings"

	"gorm.io/gorm"

	"lazyrag/core/common/orm"
)

type SuggestionOutdatedResolver struct {
	db    *gorm.DB
	cache map[string]suggestionHashState
}

type suggestionHashState struct {
	found bool
	hash  string
}

func NewSuggestionOutdatedResolver(db *gorm.DB) *SuggestionOutdatedResolver {
	return &SuggestionOutdatedResolver{
		db:    db,
		cache: map[string]suggestionHashState{},
	}
}

func (r *SuggestionOutdatedResolver) Resolve(ctx context.Context, row orm.ResourceSuggestion) (bool, error) {
	if r == nil || r.db == nil {
		return false, nil
	}
	if strings.TrimSpace(row.ResourceType) != ResourceTypeSkill {
		return false, nil
	}

	snapshotHash := strings.TrimSpace(row.SnapshotHash)
	currentHash, found, err := r.currentSkillHash(ctx, row.UserID, firstNonEmpty(row.ResourceKey, row.RelativePath))
	if err != nil {
		return false, err
	}
	if !found {
		return snapshotHash != "", nil
	}
	if snapshotHash == "" {
		return true, nil
	}
	return currentHash != snapshotHash, nil
}

func (r *SuggestionOutdatedResolver) currentSkillHash(ctx context.Context, userID, resourceKey string) (string, bool, error) {
	key := strings.TrimSpace(userID) + "\n" + strings.TrimSpace(resourceKey)
	if cached, ok := r.cache[key]; ok {
		return cached.hash, cached.found, nil
	}

	state, err := LoadSkillStateByResourceKey(ctx, r.db, userID, resourceKey)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		r.cache[key] = suggestionHashState{}
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}

	hash := strings.TrimSpace(state.ContentHash)
	r.cache[key] = suggestionHashState{found: true, hash: hash}
	return hash, true, nil
}
