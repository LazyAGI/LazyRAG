package skill

import (
	"lazyrag/core/evolution"
)

func buildContentDiff(currentContent, draftContent string) (string, error) {
	return evolution.BuildContentDiff(currentContent, draftContent)
}
