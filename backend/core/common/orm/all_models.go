// all_models 提供与 orm/models.go 一致的 model 列表，供 dbmigrate migrate / create -with-ddl 生成 DDL 时使用。
// 新增 Model 时在 models.go 定义，并在本文件 AllModelsForDDL / TableNamesForDDL 中同步追加。

package orm

// AllModelsForDDL 返回需参与迁移的 model 实例列表，用于 DDL 生成。
func AllModelsForDDL() []interface{} {
	return []interface{}{
		&VisibilityModel{},
		&ACLModel{},
		&KBModel{},
		&UserGroupModel{},
		&Prompt{},
		&DefaultPrompt{},
		&MultiAnswersSwitch{},
		&Conversation{},
		&ChatHistory{},
		&MultiAnswersChatHistory{},
	}
}

// TableNamesForDDL 返回与 AllModelsForDDL 顺序一致的表名列表，用于生成 DROP TABLE（逆序）。
func TableNamesForDDL() []string {
	return []string{
		"acl_visibility",
		"acl_rows",
		"acl_kbs",
		"acl_user_groups",
		"prompts",
		"default_prompts",
		"multi_answers_switches",
		"conversations",
		"chat_histories",
		"multi_answers_chat_histories",
	}
}
