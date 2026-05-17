package doc

import "testing"

func TestParseReparseTaskIDsAcceptsWrappedDocServerResponse(t *testing.T) {
	var resp reparseResponse
	resp.Data.TaskIDs = []string{"reparse-task-1"}

	got := parseReparseTaskIDs(resp)
	if len(got) != 1 || got[0] != "reparse-task-1" {
		t.Fatalf("expected wrapped reparse task id, got %#v", got)
	}
}

func TestParseReparseTaskIDsPrefersTopLevelTaskIDs(t *testing.T) {
	resp := reparseResponse{TaskIDs: []string{"top-level-task"}}
	resp.Data.TaskIDs = []string{"wrapped-task"}

	got := parseReparseTaskIDs(resp)
	if len(got) != 1 || got[0] != "top-level-task" {
		t.Fatalf("expected top-level reparse task id, got %#v", got)
	}
}
