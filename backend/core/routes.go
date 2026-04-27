package main

import (
	"lazyrag/core/acl"
	"lazyrag/core/chat"
	"lazyrag/core/doc"
	"lazyrag/core/file"
	"lazyrag/core/wordgroup"

	"github.com/gorilla/mux"
)

// registerAllRoutes text OpenAPI text（text Job），text handleAPI textPermissiontext（text extract_api_permissions.py text Kong RBAC）。
func registerAllRoutes(r *mux.Router) {
	// ----- Datasettext -----
	handleAPI(r, "GET", "/dataset/algos", []string{"document.read"}, doc.ListAlgos)
	handleAPI(r, "GET", "/dataset/tags", []string{"document.read"}, doc.AllDatasetTags)
	handleAPI(r, "GET", "/datasets", []string{"document.read"}, doc.ListDatasets)
	handleAPI(r, "POST", "/datasets", []string{"document.write"}, doc.CreateDataset)
	handleAPI(r, "GET", "/datasets/{dataset}", []string{"document.read"}, doc.GetDataset)
	handleAPI(r, "DELETE", "/datasets/{dataset}", []string{"document.write"}, doc.DeleteDataset)
	handleAPI(r, "PATCH", "/datasets/{dataset}", []string{"document.write"}, doc.UpdateDataset)
	handleAPI(r, "POST", "/datasets/{dataset}:setDefault", []string{"document.read"}, doc.SetDefault)
	handleAPI(r, "POST", "/datasets/{dataset}:unsetDefault", []string{"document.read"}, doc.UnsetDefault)

	// ----- DocumentService -----
	handleAPI(r, "GET", "/datasets/{dataset}/documents", []string{"document.read"}, doc.ListDocuments)
	handleAPI(r, "POST", "/datasets/{dataset}/documents", []string{"document.write"}, doc.CreateDocument)
	// :content/:download text {document} text，text /documents/xxx:content text {document} text。
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}:content", []string{"document.read"}, doc.GetDocumentContent)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}:download", []string{"document.read"}, doc.DownloadDocument)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}", []string{"document.read"}, doc.GetDocument)
	handleAPI(r, "DELETE", "/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.DeleteDocument)
	handleAPI(r, "PATCH", "/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.UpdateDocument)
	handleAPI(r, "POST", "/datasets/{dataset}/documents:search", []string{"document.read"}, doc.SearchDocuments)
	handleAPI(r, "POST", "/datasets/{dataset}/documents:batchUpdateTags", []string{"document.write"}, doc.BatchUpdateDocumentTags)
	handleAPI(r, "POST", "/documents:search", []string{"document.read"}, doc.SearchAllDocuments)
	handleAPI(r, "POST", "/datasets/{dataset}:batchDelete", []string{"document.write"}, doc.BatchDeleteDocument)
	handleAPI(r, "GET", "/document/creators", []string{"document.read"}, doc.AllDocumentCreators)
	handleAPI(r, "GET", "/document/tags", []string{"document.read"}, doc.AllDocumentTags)
	// ----- text -----
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/segments", []string{"document.read"}, doc.ListSegments)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/segments/{segment}", []string{"document.read"}, doc.GetSegment)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/segments:search", []string{"document.read"}, doc.SearchSegments)

	// ----- DatasetMembertext -----
	handleAPI(r, "GET", "/datasets/{dataset}/members", []string{"document.read"}, doc.ListDatasetMembers)
	handleAPI(r, "GET", "/datasets/{dataset}/members/{user_id}", []string{"document.read"}, doc.GetDatasetMember)
	handleAPI(r, "DELETE", "/datasets/{dataset}/members/{user_id}", []string{"document.write"}, doc.DeleteDatasetMember)
	handleAPI(r, "PATCH", "/datasets/{dataset}/members/{user_id}", []string{"document.write"}, doc.UpdateDatasetMember)
	handleAPI(r, "DELETE", "/datasets/{dataset}/members/groups/{group_id}", []string{"document.write"}, doc.DeleteDatasetGroupMember)
	handleAPI(r, "PATCH", "/datasets/{dataset}/members/groups/{group_id}", []string{"document.write"}, doc.UpdateDatasetGroupMember)
	handleAPI(r, "POST", "/datasets/{dataset}/members:search", []string{"document.read"}, doc.SearchDatasetMember)
	handleAPI(r, "POST", "/datasets/{dataset}:batchAddMember", []string{"document.write"}, doc.BatchAddDatasetMember)

	// ----- Tasktext（text Task，text Job） -----
	handleAPI(r, "GET", "/datasets/{dataset}/tasks", []string{"document.read"}, doc.ListTasks)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks", []string{"document.write"}, doc.CreateTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks:search", []string{"document.read"}, doc.SearchTasks)
	handleAPI(r, "POST", "/datasets/{dataset}/uploads", []string{"document.write"}, doc.UploadFile)
	handleAPI(r, "POST", "/temp/uploads", []string{"document.write"}, doc.UploadTempFile)
	handleAPI(r, "POST", "/temp/uploads:initUpload", []string{"document.write"}, doc.InitTempUpload)
	handleAPI(r, "PUT", "/temp/uploads/{upload_id}/parts/{part_number}", []string{"document.write"}, doc.UploadTempPart)
	handleAPI(r, "POST", "/temp/uploads/{upload_id}:complete", []string{"document.write"}, doc.CompleteTempUpload)
	handleAPI(r, "POST", "/temp/uploads/{upload_id}:abort", []string{"document.write"}, doc.AbortTempUpload)
	handleAPI(r, "GET", "/datasets/{dataset}/uploads/{upload_file_id}:content", []string{"document.read"}, doc.GetUploadedFileContent)
	handleAPI(r, "GET", "/datasets/{dataset}/uploads/{upload_file_id}:download", []string{"document.read"}, doc.DownloadUploadedFile)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks:batchUpload", []string{"document.write"}, doc.BatchUploadTasks)
	handleAPI(r, "GET", "/datasets/{dataset}/tasks/{task}", []string{"document.read"}, doc.GetTask)
	handleAPI(r, "DELETE", "/datasets/{dataset}/tasks/{task}", []string{"document.write"}, doc.DeleteTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks:start", []string{"document.write"}, doc.StartTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:resume", []string{"document.write"}, doc.ResumeTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:suspend", []string{"document.write"}, doc.SuspendTask)
	handleAPI(r, "POST", "/datasets/{dataset}/uploads:initUpload", []string{"document.write"}, doc.InitUpload)
	handleAPI(r, "PUT", "/datasets/{dataset}/uploads/{upload_id}/parts/{part_number}", []string{"document.write"}, doc.UploadPart)
	handleAPI(r, "POST", "/datasets/{dataset}/uploads/{upload_id}:complete", []string{"document.write"}, doc.CompleteUpload)
	handleAPI(r, "POST", "/datasets/{dataset}/uploads/{upload_id}:abort", []string{"document.write"}, doc.AbortUpload)
	// text URL：text，text :file text。
	handleAPI(r, "GET", "/static-files/{path:.*}", nil, doc.GetSignedStaticFile)

	// ----- RAG text（text） -----
	handleAPI(r, "POST", "/upload_files", []string{"document.write"}, file.UploadFiles)
	handleAPI(r, "POST", "/add_files_to_group", []string{"document.write"}, file.AddFilesToGroup)
	handleAPI(r, "GET", "/list_files", []string{"document.read"}, file.ListFiles)
	handleAPI(r, "GET", "/list_files_in_group", []string{"document.read"}, file.ListFilesInGroup)
	handleAPI(r, "GET", "/list_kb_groups", []string{"document.read"}, file.ListKBGroups)

	// ----- text -----
	handleAPI(r, "POST", "/chat", []string{"qa.read"}, chat.Chat)

	// ----- Conversationtext -----
	handleAPI(r, "POST", "/conversations:chat", []string{"qa.read"}, chat.ChatConversations)
	handleAPI(r, "POST", "/conversations:resumeChat", []string{"qa.read"}, chat.ResumeChat)
	handleAPI(r, "POST", "/conversations:stopChatGeneration", []string{"qa.read"}, chat.StopChatGeneration)
	handleAPI(r, "GET", "/conversations/{conversation_id}:status", []string{"qa.read"}, chat.GetChatStatus)

	// :detail text {name} text，text /conversations/xxx:detail text {name} text GetConversation（text history）
	handleAPI(r, "GET", "/conversations/{name}:detail", []string{"qa.read"}, chat.GetConversationDetail)
	handleAPI(r, "GET", "/conversations/{name}", []string{"qa.read"}, chat.GetConversation)
	handleAPI(r, "DELETE", "/conversations/{name}", []string{"qa.read"}, chat.DeleteConversation)
	handleAPI(r, "POST", "/conversations:batchDelete", []string{"qa.read"}, chat.BatchDeleteConversations)
	handleAPI(r, "GET", "/conversations", []string{"qa.read"}, chat.ListConversations)
	handleAPI(r, "POST", "/conversations:setChatHistory", []string{"qa.read"}, chat.SetChatHistory)
	handleAPI(r, "POST", "/conversations:feedBackChatHistory", []string{"qa.read"}, chat.FeedBackChatHistory)

	handleAPI(r, "GET", "/conversation:switchStatus", []string{"qa.read"}, chat.GetMultiAnswersSwitchStatus)
	handleAPI(r, "POST", "/conversation:switchStatus", []string{"qa.read"}, chat.SetMultiAnswersSwitchStatus)
	handleAPI(r, "POST", "/conversation:export", []string{"qa.read"}, chat.ExportConversations)
	handleAPI(r, "GET", "/conversation:export/files/{file_id}", []string{"qa.read"}, chat.DownloadExportConversationFile)

	// ----- Word group -----
	handleAPI(r, "POST", "/word_group:checkExists", []string{}, wordgroup.CheckWordsExist)
	handleAPI(r, "DELETE", "/word_group/{group_id}", []string{}, wordgroup.DeleteWordGroup)
	handleAPI(r, "POST", "/word_group:batchDelete", []string{}, wordgroup.BatchDeleteWordGroups)
	handleAPI(r, "POST", "/word_group", []string{}, wordgroup.CreateWordGroup)

	// ----- Prompttext -----
	handleAPI(r, "POST", "/prompts", []string{"document.write"}, chat.CreatePrompt)
	// :setDefault/:unsetDefault text {name} text，text :action text。
	handleAPI(r, "POST", "/prompts/{name}:setDefault", []string{"document.write"}, chat.SetDefaultPrompt)
	handleAPI(r, "POST", "/prompts/{name}:unsetDefault", []string{"document.write"}, chat.UnsetDefaultPrompt)
	handleAPI(r, "PATCH", "/prompts/{name}", []string{"document.write"}, chat.UpdatePrompt)
	handleAPI(r, "DELETE", "/prompts/{name}", []string{"document.write"}, chat.DeletePrompt)
	handleAPI(r, "GET", "/prompts/{name}", []string{"document.read"}, chat.GetPrompt)
	handleAPI(r, "GET", "/prompts", []string{"document.read"}, chat.ListPrompts)

	// ----- ACL（Knowledge basetextPermission） -----
	handleAPI(r, "GET", "/kb/list", []string{"document.read"}, acl.ListKB)
	handleAPI(r, "POST", "/kb/permission/batch", []string{"document.read"}, acl.PermissionBatch)
	handleAPI(r, "GET", "/kb/{kb_id}/permission", []string{"document.read"}, acl.GetPermission)
	handleAPI(r, "GET", "/kb/{kb_id}/can", []string{"document.read"}, acl.CanHandler)
	handleAPI(r, "GET", "/kb/{kb_id}/acl", []string{"document.read"}, acl.ListACL)
	handleAPI(r, "POST", "/kb/{kb_id}/acl", []string{"document.write"}, acl.AddACL)
	handleAPI(r, "POST", "/kb/{kb_id}/acl/batch", []string{"document.write"}, acl.BatchAddACL)
	handleAPI(r, "PUT", "/kb/{kb_id}/acl/{acl_id}", []string{"document.write"}, acl.UpdateACL)
	handleAPI(r, "DELETE", "/kb/{kb_id}/acl/{acl_id}", []string{"document.write"}, acl.DeleteACL)
	handleAPI(r, "GET", "/kb/{kb_id}/authorization", []string{"document.read"}, acl.GetKBAuthorization)
	handleAPI(r, "POST", "/kb/{kb_id}/authorization", []string{"document.write"}, acl.SetKBAuthorization)
	handleAPI(r, "GET", "/kb/grant-principals", []string{"document.read"}, acl.ListGrantPrincipals)
}
