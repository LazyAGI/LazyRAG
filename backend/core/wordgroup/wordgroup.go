package wordgroup

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"

	"gorm.io/gorm"
)

// CreateWordGroupRequest is the JSON body for POST /word_group.
// 一次提交一个术语及可选的多个别名（aliases）。
type CreateWordGroupRequest struct {
	Term        string   `json:"term"`
	Aliases     []string `json:"aliases"`
	Description string   `json:"description"`
	Lock        bool     `json:"lock"` // 保护态
}

// CreatedAlias is one persisted alias row under a term.
type CreatedAlias struct {
	ID   string `json:"id"`
	Word string `json:"word"`
}

// CreateWordGroupResponse is returned in APIResponse.Data after create.
type CreateWordGroupResponse struct {
	TermID      string         `json:"term_id"`
	Term        string         `json:"term"`
	GroupID     string         `json:"group_id"`
	Aliases     []CreatedAlias `json:"aliases"`
	Description string         `json:"description"`
	Source      string         `json:"source"`
	Reference   string         `json:"reference"`
	Lock        bool           `json:"lock"`
}

// CreateWordGroup persists one term row and zero or more alias rows (same group / metadata).
func CreateWordGroup(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body CreateWordGroupRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	term := strings.TrimSpace(body.Term)
	groupID := GenerateID()
	desc := strings.TrimSpace(body.Description)
	ref := ""
	src := normalizeSource("")
	aliases := normalizeAliases(body.Aliases)

	if term == "" {
		common.ReplyErr(w, "term is required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	userName := store.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	now := time.Now().UTC()
	base := orm.BaseModel{
		CreateUserID:   userID,
		CreateUserName: userName,
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	var termID string
	var createdAliases []CreatedAlias

	err := store.DB().Transaction(func(tx *gorm.DB) error {
		termID = GenerateID()
		termRow := orm.Word{
			ID:            termID,
			Word:          term,
			WordKind:      orm.WordKindTerm,
			GroupID:       groupID,
			Description:   desc,
			Source:        src,
			ReferenceInfo: ref,
			Locked:        body.Lock,
			BaseModel:     base,
		}
		if err := tx.Create(&termRow).Error; err != nil {
			return err
		}
		for _, a := range aliases {
			aid := GenerateID()
			ar := orm.Word{
				ID:            aid,
				Word:          a,
				WordKind:      orm.WordKindAlias,
				GroupID:       groupID,
				Description:   desc,
				Source:        src,
				ReferenceInfo: ref,
				Locked:        body.Lock,
				BaseModel:     base,
			}
			if err := tx.Create(&ar).Error; err != nil {
				return err
			}
			createdAliases = append(createdAliases, CreatedAlias{ID: aid, Word: a})
		}
		return nil
	})
	if err != nil {
		log.Logger.Error().Err(err).Str("term_id", termID).Msg("create word_group rows failed")
		common.ReplyErr(w, "create word group failed", http.StatusInternalServerError)
		return
	}

	common.ReplyOK(w, CreateWordGroupResponse{
		TermID:      termID,
		Term:        term,
		GroupID:     groupID,
		Aliases:     createdAliases,
		Description: desc,
		Source:      src,
		Reference:   ref,
		Lock:        body.Lock,
	})
}

func normalizeAliases(raw []string) []string {
	var out []string
	for _, s := range raw {
		s = strings.TrimSpace(s)
		if s == "" {
			continue
		}
		out = append(out, s)
	}
	return out
}

func normalizeSource(s string) string {
	s = strings.TrimSpace(strings.ToLower(s))
	switch s {
	case "", "user", "用户":
		return "user"
	case "ai", "系统":
		return "ai"
	default:
		return ""
	}
}

// GenerateID returns a random 32-char hex id (UUID v4, no dashes). Each call is independent.
func GenerateID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(fmt.Sprintf("wordgroup.GenerateID: %v", err))
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return hex.EncodeToString(b[:])
}
