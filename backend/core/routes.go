package main

import (
	"github.com/gorilla/mux"
	"lazyrag/core/chat"
	"lazyrag/core/db"
	"lazyrag/core/doc"
)

// registerAllRoutes 注册 openapi 中除 Job 外的所有接口，并集中使用 handleAPI 做 RBAC（供 extract_api_permissions.py 提取）。
func registerAllRoutes(r *mux.Router) {
	// ----- DatasetService -----
	handleAPI(r, "GET", "/api/v1/dataset/algos", []string{"document.read"}, doc.ListAlgos)
	handleAPI(r, "GET", "/api/v1/dataset/tags", []string{"document.read"}, doc.AllDatasetTags)
	handleAPI(r, "GET", "/api/v1/datasets", []string{"document.read"}, doc.ListDatasets)
	handleAPI(r, "POST", "/api/v1/datasets", []string{"document.write"}, doc.CreateDataset)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}", []string{"document.read"}, doc.GetDataset)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}", []string{"document.write"}, doc.DeleteDataset)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}", []string{"document.write"}, doc.UpdateDataset)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:setDefault", []string{"document.write"}, doc.SetDefault)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:unsetDefault", []string{"document.write"}, doc.UnsetDefault)
	handleAPI(r, "GET", "/api/v1/datasets:allDefaultDatasets", []string{"document.read"}, doc.AllDefaultDatasets)
	handleAPI(r, "POST", "/api/v1/datasets:presignUploadCoverImageUrl", []string{"document.write"}, doc.PresignUploadCoverImageURL)
	handleAPI(r, "POST", "/api/v1/datasets:search", []string{"document.read"}, doc.SearchDatasets)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks:callback", []string{"document.write"}, doc.CallbackTask)

	// ----- DocumentService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents", []string{"document.read"}, doc.ListDocuments)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents", []string{"document.write"}, doc.CreateDocument)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.read"}, doc.GetDocument)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.DeleteDocument)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, doc.UpdateDocument)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents:search", []string{"document.read"}, doc.SearchDocuments)
	handleAPI(r, "POST", "/api/v1/documents:search", []string{"document.read"}, doc.SearchAllDocuments)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:batchDelete", []string{"document.write"}, doc.BatchDeleteDocument)
	handleAPI(r, "GET", "/api/v1/document/creators", []string{"document.read"}, doc.AllDocumentCreators)
	handleAPI(r, "GET", "/api/v1/document/tags", []string{"document.read"}, doc.AllDocumentTags)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:add", []string{"document.write"}, doc.AddTableData)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:batchDelete", []string{"document.write"}, doc.BatchDeleteTableData)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:modify", []string{"document.write"}, doc.ModifyTableData)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table:search", []string{"document.read"}, doc.SearchTableData)

	// ----- SegmentService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments", []string{"document.read"}, doc.ListSegments)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}", []string{"document.read"}, doc.GetSegment)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:edit", []string{"document.write"}, doc.EditSegment)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:modifyStatus", []string{"document.write"}, doc.ModifyStatus)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments:search", []string{"document.read"}, doc.SearchSegments)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/group/{group}/documents/{document}/segments/{segment}", []string{"document.write"}, doc.DeleteSegment)
	handleAPI(r, "POST", "/api/v1/segment/imageURIs:batchSign", []string{"document.read"}, doc.BatchSignImageURI)
	handleAPI(r, "POST", "/api/v1/segments:bulkDelete", []string{"document.write"}, doc.BulkDelete)
	handleAPI(r, "POST", "/api/v1/segments:hybrid", []string{"document.read"}, doc.HybridSearchSegments)
	handleAPI(r, "POST", "/api/v1/segments:scroll", []string{"document.read"}, doc.ScrollSegments)

	// ----- TableService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table/meta", []string{"document.read"}, db.GetMeta)
	handleAPI(r, "POST", "/api/v1/table:findMeta", []string{"document.read"}, db.FindMeta)
	handleAPI(r, "POST", "/api/v1/table:query", []string{"document.read"}, db.QueryTable)

	// ----- DatasetMemberService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/members", []string{"document.read"}, doc.ListDatasetMembers)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.read"}, doc.GetDatasetMember)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, doc.DeleteDatasetMember)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, doc.UpdateDatasetMember)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/members:search", []string{"document.read"}, doc.SearchDatasetMember)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:batchAddMember", []string{"document.write"}, doc.BatchAddDatasetMember)

	// ----- TaskService（直接暴露 Task，不再通过 Job）-----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/tasks", []string{"document.read"}, doc.ListTasks)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks", []string{"document.write"}, doc.CreateTask)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.read"}, doc.GetTask)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.write"}, doc.DeleteTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:cancel", []string{"document.write"}, doc.CancelTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:suspend", []string{"document.write"}, doc.SuspendTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:resume", []string{"document.write"}, doc.ResumeTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:callback", []string{"document.write"}, doc.TaskCallback)

	// ----- ChatService -----
	handleAPI(r, "POST", "/api/chat", []string{"qa.read"}, chat.Chat)
	handleAPI(r, "POST", "/api/chat/stream", []string{"qa.read"}, chat.ChatStream)

	// ----- DatabaseService (RAG databases) -----
	handleAPI(r, "GET", "/api/v1/rag/database/tags", []string{"document.read"}, db.GetUserDatabaseTags)
	handleAPI(r, "POST", "/api/v1/rag/databases", []string{"document.read"}, db.GetUserDatabases)
	handleAPI(r, "POST", "/api/v1/rag/databases/create", []string{"document.write"}, db.CreateDatabase)
	handleAPI(r, "GET", "/api/v1/rag/databases/summary", []string{"document.read"}, db.GetUserDatabaseSummaries)
	handleAPI(r, "POST", "/api/v1/rag/databases/validate-connection", []string{"document.write"}, db.ValidateConnection)
	handleAPI(r, "DELETE", "/api/v1/rag/databases/{database_id}", []string{"document.write"}, db.DeleteDatabase)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables", []string{"document.read"}, db.GetDatabaseTables)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/cell", []string{"document.write"}, db.UpdateTableCell)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/preview", []string{"document.read"}, db.ListTableRows)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/update", []string{"document.write"}, db.UpdateDatabase)

	// ----- Internal -----
	handleAPI(r, "GET", "/api/v1/inner/datasets/{dataset}:internal", []string{"document.read"}, doc.GetDatasetInternal)
	handleAPI(r, "POST", "/api/v1/inner/rag:knowledgeRetrieve", []string{"qa.read"}, doc.KnowledgeRetrieve)

	// ----- WriterSegmentJob -----
	handleAPI(r, "POST", "/api/v1/writerSegmentJob:submit", []string{"document.write"}, doc.Submit)
	handleAPI(r, "GET", "/api/v1/writerSegmentJobs/{writerSegmentJob}", []string{"document.read"}, doc.Get)
}
