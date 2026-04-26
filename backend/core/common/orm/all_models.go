// all_models text orm/models.go text model text，text dbmigrate migrate / create -with-ddl text DDL text。
// text Model text models.go text，text AllModelsForDDL / TableNamesForDDL text。

package orm

// AllModelsForDDL text model text，text DDL text。
func AllModelsForDDL() []interface{} {
	return []interface{}{
		&VisibilityModel{},
		&ACLModel{},
		&KBModel{},
		&ACLGroupModel{},
		&UserGroupModel{},
		&Prompt{},
		&DefaultPrompt{},
		&MultiAnswersSwitch{},
		&Conversation{},
		&ChatHistory{},
		&MultiAnswersChatHistory{},
		&Dataset{},
		&DefaultDataset{},
		&Document{},
		&Task{},
		&UploadSession{},
		&UploadedFile{},
		&Word{},
	}
}

// TableNamesForDDL text AllModelsForDDL text，text DROP TABLE（text）。
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
		"datasets",
		"default_datasets",
		"documents",
		"tasks",
		"upload_sessions",
		"uploaded_files",
		"words",
	}
}
