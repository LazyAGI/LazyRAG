package main

import (
	"lazyrag/core/acl"
	"lazyrag/core/chat"
	"lazyrag/core/db"
	"lazyrag/core/doc"
	"lazyrag/core/file"

	"github.com/gorilla/mux"
)

// registerAllRoutes 注册全部 OpenAPI 路由（不含 Job），经 handleAPI 挂载权限信息（供 extract_api_permissions.py 生成 Kong RBAC）。
func registerAllRoutes(r *mux.Router) {
	// ----- 数据集服务 -----
	handleAPI(r, "GET", "/dataset/algos", []string{"document.read"}, doc.ListAlgos)
	handleAPI(r, "GET", "/dataset/tags", []string{"document.read"}, doc.AllDatasetTags)
	handleAPI(r, "GET", "/datasets", []string{"document.read"}, doc.ListDatasets)
	handleAPI(r, "POST", "/datasets", []string{"document.write"}, doc.CreateDataset)
	handleAPI(r, "GET", "/datasets/{dataset}", []string{"document.read"}, doc.GetDataset)
	handleAPI(r, "DELETE", "/datasets/{dataset}", []string{"document.write"}, doc.DeleteDataset)
	handleAPI(r, "PATCH", "/datasets/{dataset}", []string{"document.write"}, doc.UpdateDataset)
	handleAPI(r, "POST", "/datasets/{dataset}:setDefault", []string{"document.write"}, doc.SetDefault)
	handleAPI(r, "POST", "/datasets/{dataset}:unsetDefault", []string{"document.write"}, doc.UnsetDefault)
	handleAPI(r, "GET", "/datasets:allDefaultDatasets", []string{"document.read"}, doc.AllDefaultDatasets)
	handleAPI(r, "POST", "/datasets:presignUploadCoverImageUrl", []string{"document.write"}, doc.PresignUploadCoverImageURL)
	handleAPI(r, "POST", "/datasets:search", []string{"document.read"}, doc.SearchDatasets)
	// 数据集级回调（路径中无 task id）
	handleAPI(r, "POST", "/datasets/{dataset}/tasks:callback", []string{"document.write"}, doc.CallbackTask)

	// ----- DocumentService -----
	handleAPI(r, "GET", "/datasets/{dataset}/documents", []string{"document.read"}, doc.ListDocuments)
	handleAPI(r, "POST", "/datasets/{dataset}/documents", []string{"document.write"}, doc.CreateDocument)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}", []string{"document.read"}, doc.GetDocument)
	handleAPI(r, "DELETE", "/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.DeleteDocument)
	handleAPI(r, "PATCH", "/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.UpdateDocument)
	handleAPI(r, "POST", "/datasets/{dataset}/documents:search", []string{"document.read"}, doc.SearchDocuments)
	handleAPI(r, "POST", "/documents:search", []string{"document.read"}, doc.SearchAllDocuments)
	handleAPI(r, "POST", "/datasets/{dataset}:batchDelete", []string{"document.write"}, doc.BatchDeleteDocument)
	handleAPI(r, "GET", "/document/creators", []string{"document.read"}, doc.AllDocumentCreators)
	handleAPI(r, "GET", "/document/tags", []string{"document.read"}, doc.AllDocumentTags)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/table:add", []string{"document.write"}, doc.AddTableData)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/table:batchDelete", []string{"document.write"}, doc.BatchDeleteTableData)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/table:modify", []string{"document.write"}, doc.ModifyTableData)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/table:search", []string{"document.read"}, doc.SearchTableData)

	// ----- 分段服务 -----
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/segments", []string{"document.read"}, doc.ListSegments)
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/segments/{segment}", []string{"document.read"}, doc.GetSegment)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/segments/{segment}:edit", []string{"document.write"}, doc.EditSegment)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/segments/{segment}:modifyStatus", []string{"document.write"}, doc.ModifyStatus)
	handleAPI(r, "POST", "/datasets/{dataset}/documents/{document}/segments:search", []string{"document.read"}, doc.SearchSegments)
	handleAPI(r, "DELETE", "/datasets/{dataset}/group/{group}/documents/{document}/segments/{segment}", []string{"document.write"}, doc.DeleteSegment)
	handleAPI(r, "POST", "/segment/imageURIs:batchSign", []string{"document.read"}, doc.BatchSignImageURI)
	handleAPI(r, "POST", "/segments:bulkDelete", []string{"document.write"}, doc.BulkDelete)
	handleAPI(r, "POST", "/segments:hybrid", []string{"document.read"}, doc.HybridSearchSegments)
	handleAPI(r, "POST", "/segments:scroll", []string{"document.read"}, doc.ScrollSegments)

	// ----- 表格服务 -----
	handleAPI(r, "GET", "/datasets/{dataset}/documents/{document}/table/meta", []string{"document.read"}, db.GetMeta)
	handleAPI(r, "POST", "/table:findMeta", []string{"document.read"}, db.FindMeta)
	handleAPI(r, "POST", "/table:query", []string{"document.read"}, db.QueryTable)

	// ----- 数据集成员服务 -----
	handleAPI(r, "GET", "/datasets/{dataset}/members", []string{"document.read"}, doc.ListDatasetMembers)
	handleAPI(r, "GET", "/datasets/{dataset}/members/{member}", []string{"document.read"}, doc.GetDatasetMember)
	handleAPI(r, "DELETE", "/datasets/{dataset}/members/{member}", []string{"document.write"}, doc.DeleteDatasetMember)
	handleAPI(r, "PATCH", "/datasets/{dataset}/members/{member}", []string{"document.write"}, doc.UpdateDatasetMember)
	handleAPI(r, "POST", "/datasets/{dataset}/members:search", []string{"document.read"}, doc.SearchDatasetMember)
	handleAPI(r, "POST", "/datasets/{dataset}:batchAddMember", []string{"document.write"}, doc.BatchAddDatasetMember)

	// ----- 任务服务（直接暴露 Task，不经 Job） -----
	handleAPI(r, "GET", "/datasets/{dataset}/tasks", []string{"document.read"}, doc.ListTasks)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks", []string{"document.write"}, doc.CreateTask)
	handleAPI(r, "GET", "/datasets/{dataset}/tasks/{task}", []string{"document.read"}, doc.GetTask)
	handleAPI(r, "DELETE", "/datasets/{dataset}/tasks/{task}", []string{"document.write"}, doc.DeleteTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:cancel", []string{"document.write"}, doc.CancelTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:suspend", []string{"document.write"}, doc.SuspendTask)
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:resume", []string{"document.write"}, doc.ResumeTask)
	// 任务级回调（路径中含 task id）
	handleAPI(r, "POST", "/datasets/{dataset}/tasks/{task}:callback", []string{"document.write"}, doc.TaskCallback)

	// ----- RAG 文件服务（代理到解析服务） -----
	handleAPI(r, "POST", "/upload_files", []string{"document.write"}, file.UploadFiles)
	handleAPI(r, "POST", "/add_files_to_group", []string{"document.write"}, file.AddFilesToGroup)
	handleAPI(r, "GET", "/list_files", []string{"document.read"}, file.ListFiles)
	handleAPI(r, "GET", "/list_files_in_group", []string{"document.read"}, file.ListFilesInGroup)
	handleAPI(r, "GET", "/list_kb_groups", []string{"document.read"}, file.ListKBGroups)

	// ----- 对话服务 -----
	handleAPI(r, "POST", "/chat", []string{"qa.read"}, chat.Chat)

	// ----- 会话服务 -----
	handleAPI(r, "POST", "/conversations:chat", []string{"qa.read"}, chat.ChatConversations)
	handleAPI(r, "POST", "/conversations:resumeChat", []string{"qa.read"}, chat.ResumeChat)
	handleAPI(r, "POST", "/conversations:stopChatGeneration", []string{"qa.read"}, chat.StopChatGeneration)
	handleAPI(r, "GET", "/conversations/{conversation_id}:status", []string{"qa.read"}, chat.GetChatStatus)

	// :detail 必须先于 {name} 注册，否则 /conversations/xxx:detail 会被 {name} 匹配成 GetConversation（无 history）
	handleAPI(r, "GET", "/conversations/{name}:detail", []string{"qa.read"}, chat.GetConversationDetail)
	handleAPI(r, "GET", "/conversations/{name}", []string{"qa.read"}, chat.GetConversation)
	handleAPI(r, "DELETE", "/conversations/{name}", []string{"qa.read"}, chat.DeleteConversation)
	handleAPI(r, "GET", "/conversations", []string{"qa.read"}, chat.ListConversations)
	handleAPI(r, "POST", "/conversations:setChatHistory", []string{"qa.read"}, chat.SetChatHistory)
	handleAPI(r, "POST", "/conversations:feedBackChatHistory", []string{"qa.read"}, chat.FeedBackChatHistory)

	handleAPI(r, "GET", "/conversation:switchStatus", []string{"qa.read"}, chat.GetMultiAnswersSwitchStatus)
	handleAPI(r, "POST", "/conversation:switchStatus", []string{"qa.read"}, chat.SetMultiAnswersSwitchStatus)

	// ----- 提示词服务 -----
	handleAPI(r, "POST", "/prompts", []string{"document.write"}, chat.CreatePrompt)
	handleAPI(r, "PATCH", "/prompts/{name}", []string{"document.write"}, chat.UpdatePrompt)
	handleAPI(r, "DELETE", "/prompts/{name}", []string{"document.write"}, chat.DeletePrompt)
	handleAPI(r, "GET", "/prompts/{name}", []string{"document.read"}, chat.GetPrompt)
	handleAPI(r, "GET", "/prompts", []string{"document.read"}, chat.ListPrompts)
	handleAPI(r, "POST", "/prompts/{name}:setDefault", []string{"document.write"}, chat.SetDefaultPrompt)
	handleAPI(r, "POST", "/prompts/{name}:unsetDefault", []string{"document.write"}, chat.UnsetDefaultPrompt)

	// ----- 数据库服务（RAG 数据库） -----
	handleAPI(r, "GET", "/rag/database/tags", []string{"document.read"}, db.GetUserDatabaseTags)
	handleAPI(r, "POST", "/rag/databases", []string{"document.read"}, db.GetUserDatabases)
	handleAPI(r, "POST", "/rag/databases/create", []string{"document.write"}, db.CreateDatabase)
	handleAPI(r, "GET", "/rag/databases/summary", []string{"document.read"}, db.GetUserDatabaseSummaries)
	handleAPI(r, "POST", "/rag/databases/validate-connection", []string{"document.write"}, db.ValidateConnection)
	handleAPI(r, "DELETE", "/rag/databases/{database_id}", []string{"document.write"}, db.DeleteDatabase)
	handleAPI(r, "POST", "/rag/databases/{database_id}/tables", []string{"document.read"}, db.GetDatabaseTables)
	handleAPI(r, "POST", "/rag/databases/{database_id}/tables/{table_id}/cell", []string{"document.write"}, db.UpdateTableCell)
	handleAPI(r, "POST", "/rag/databases/{database_id}/tables/{table_id}/preview", []string{"document.read"}, db.ListTableRows)
	handleAPI(r, "POST", "/rag/databases/{database_id}/update", []string{"document.write"}, db.UpdateDatabase)

	// ----- 内部接口 -----
	handleAPI(r, "GET", "/inner/datasets/{dataset}:internal", []string{"document.read"}, doc.GetDatasetInternal)
	handleAPI(r, "POST", "/inner/rag:knowledgeRetrieve", []string{"qa.read"}, doc.KnowledgeRetrieve)

	// ----- WriterSegmentJob -----
	handleAPI(r, "POST", "/writerSegmentJob:submit", []string{"document.write"}, doc.Submit)
	handleAPI(r, "GET", "/writerSegmentJobs/{writerSegmentJob}", []string{"document.read"}, doc.Get)

	// ----- ACL（知识库数据权限） -----
	handleAPI(r, "GET", "/kb/list", []string{"document.read"}, acl.ListKB)
	handleAPI(r, "POST", "/kb/permission/batch", []string{"document.read"}, acl.PermissionBatch)
	handleAPI(r, "GET", "/kb/{kb_id}/permission", []string{"document.read"}, acl.GetPermission)
	handleAPI(r, "GET", "/kb/{kb_id}/can", []string{"document.read"}, acl.CanHandler)
	handleAPI(r, "GET", "/kb/{kb_id}/acl", []string{"document.read"}, acl.ListACL)
	handleAPI(r, "POST", "/kb/{kb_id}/acl", []string{"document.write"}, acl.AddACL)
	handleAPI(r, "POST", "/kb/{kb_id}/acl/batch", []string{"document.write"}, acl.BatchAddACL)
	handleAPI(r, "PUT", "/kb/{kb_id}/acl/{acl_id}", []string{"document.write"}, acl.UpdateACL)
	handleAPI(r, "DELETE", "/kb/{kb_id}/acl/{acl_id}", []string{"document.write"}, acl.DeleteACL)
}
