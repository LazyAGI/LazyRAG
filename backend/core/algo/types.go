package algo

type Suggestion struct {
	Title   string `json:"title"`
	Content string `json:"content"`
	Reason  string `json:"reason,omitempty"`
}

type SkillGenerateRequest struct {
	Content      string       `json:"content"`
	Suggestions  []Suggestion `json:"suggestions"`
	UserInstruct string       `json:"user_instruct"`
}

type MemoryGenerateRequest struct {
	Content      string       `json:"content"`
	Suggestions  []Suggestion `json:"suggestions"`
	UserInstruct string       `json:"user_instruct"`
}
