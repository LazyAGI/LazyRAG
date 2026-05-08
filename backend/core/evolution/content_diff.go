package evolution

import (
	"strings"

	"github.com/pmezard/go-difflib/difflib"
)

func BuildContentDiff(currentContent, draftContent string) (string, error) {
	if currentContent == draftContent {
		return "", nil
	}

	contextLines := len(strings.Split(currentContent, "\n")) + len(strings.Split(draftContent, "\n"))
	if contextLines < 3 {
		contextLines = 3
	}

	return difflib.GetUnifiedDiffString(difflib.UnifiedDiff{
		A:        difflib.SplitLines(currentContent),
		B:        difflib.SplitLines(draftContent),
		FromFile: "current",
		ToFile:   "draft",
		Context:  contextLines,
	})
}
