package skill

import (
	"lazymind/core/evolution"
)

func buildContentDiff(currentContent, draftContent string) (string, error) {
	return evolution.BuildContentDiff(currentContent, draftContent)
}
