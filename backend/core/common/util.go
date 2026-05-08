package common

import (
	"encoding/hex"

	"github.com/google/uuid"
)

// GenerateID returns a random 32-char hex id (UUID v4, no dashes). Each call is independent.
func GenerateID() string {
	u := uuid.New()
	return hex.EncodeToString(u[:])
}
