package main

import (
	"github.com/gorilla/mux"
	"hello-kong/core/database"
	"hello-kong/core/dataset"
	"hello-kong/core/document"
	"hello-kong/core/inner"
	"hello-kong/core/member"
	"hello-kong/core/retrieval"
	"hello-kong/core/segment"
	"hello-kong/core/table"
	"hello-kong/core/task"
	"hello-kong/core/writersegmentjob"
)

// registerAllRoutes 注册 openapi 中除 Job 外的所有接口，并集中使用 handleAPI 做 RBAC（供 extract_api_permissions.py 提取）。
func registerAllRoutes(r *mux.Router) {
	// ----- DatasetService -----
	handleAPI(r, "GET", "/api/v1/dataset/algos", []string{"document.read"}, dataset.ListAlgos)
	handleAPI(r, "GET", "/api/v1/dataset/tags", []string{"document.read"}, dataset.AllDatasetTags)
	handleAPI(r, "GET", "/api/v1/datasets", []string{"document.read"}, dataset.ListDatasets)
	handleAPI(r, "POST", "/api/v1/datasets", []string{"document.write"}, dataset.CreateDataset)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}", []string{"document.read"}, dataset.GetDataset)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}", []string{"document.write"}, dataset.DeleteDataset)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}", []string{"document.write"}, dataset.UpdateDataset)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:setDefault", []string{"document.write"}, dataset.SetDefault)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:unsetDefault", []string{"document.write"}, dataset.UnsetDefault)
	handleAPI(r, "GET", "/api/v1/datasets:allDefaultDatasets", []string{"document.read"}, dataset.AllDefaultDatasets)
	handleAPI(r, "POST", "/api/v1/datasets:presignUploadCoverImageUrl", []string{"document.write"}, dataset.PresignUploadCoverImageURL)
	handleAPI(r, "POST", "/api/v1/datasets:search", []string{"document.read"}, dataset.SearchDatasets)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks:callback", []string{"document.write"}, dataset.CallbackTask)

	// ----- DocumentService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents", []string{"document.read"}, document.ListDocuments)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents", []string{"document.write"}, document.CreateDocument)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.read"}, document.GetDocument)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, document.DeleteDocument)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, document.UpdateDocument)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents:search", []string{"document.read"}, document.SearchDocuments)
	handleAPI(r, "POST", "/api/v1/documents:search", []string{"document.read"}, document.SearchAllDocuments)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:batchDelete", []string{"document.write"}, document.BatchDeleteDocument)
	handleAPI(r, "GET", "/api/v1/document/creators", []string{"document.read"}, document.AllDocumentCreators)
	handleAPI(r, "GET", "/api/v1/document/tags", []string{"document.read"}, document.AllDocumentTags)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:add", []string{"document.write"}, document.AddTableData)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:batchDelete", []string{"document.write"}, document.BatchDeleteTableData)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:modify", []string{"document.write"}, document.ModifyTableData)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table:search", []string{"document.read"}, document.SearchTableData)

	// ----- SegmentService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments", []string{"document.read"}, segment.ListSegments)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}", []string{"document.read"}, segment.GetSegment)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:edit", []string{"document.write"}, segment.EditSegment)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:modifyStatus", []string{"document.write"}, segment.ModifyStatus)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments:search", []string{"document.read"}, segment.SearchSegments)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/group/{group}/documents/{document}/segments/{segment}", []string{"document.write"}, segment.DeleteSegment)
	handleAPI(r, "POST", "/api/v1/segment/imageURIs:batchSign", []string{"document.read"}, segment.BatchSignImageURI)
	handleAPI(r, "POST", "/api/v1/segments:bulkDelete", []string{"document.write"}, segment.BulkDelete)
	handleAPI(r, "POST", "/api/v1/segments:hybrid", []string{"document.read"}, segment.HybridSearchSegments)
	handleAPI(r, "POST", "/api/v1/segments:scroll", []string{"document.read"}, segment.ScrollSegments)

	// ----- TableService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table/meta", []string{"document.read"}, table.GetMeta)
	handleAPI(r, "POST", "/api/v1/table:findMeta", []string{"document.read"}, table.FindMeta)
	handleAPI(r, "POST", "/api/v1/table:query", []string{"document.read"}, table.QueryTable)

	// ----- DatasetMemberService -----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/members", []string{"document.read"}, member.ListDatasetMembers)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.read"}, member.GetDatasetMember)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, member.DeleteDatasetMember)
	handleAPI(r, "PATCH", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, member.UpdateDatasetMember)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/members:search", []string{"document.read"}, member.SearchDatasetMember)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}:batchAddMember", []string{"document.write"}, member.BatchAddDatasetMember)

	// ----- TaskService（直接暴露 Task，不再通过 Job）-----
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/tasks", []string{"document.read"}, task.ListTasks)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks", []string{"document.write"}, task.CreateTask)
	handleAPI(r, "GET", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.read"}, task.GetTask)
	handleAPI(r, "DELETE", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.write"}, task.DeleteTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:cancel", []string{"document.write"}, task.CancelTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:suspend", []string{"document.write"}, task.SuspendTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:resume", []string{"document.write"}, task.ResumeTask)
	handleAPI(r, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:callback", []string{"document.write"}, task.CallbackTask)

	// ----- RetrievalService (search / QA) -----
	handleAPI(r, "GET", "/api/v1/search:allSearchHistory", []string{"qa.read"}, retrieval.AllSearchHistory)
	handleAPI(r, "POST", "/api/v1/search:searchKnowledge", []string{"qa.read"}, retrieval.SearchKnowledge)
	handleAPI(r, "DELETE", "/api/v1/searchHistories/{searchHistory}", []string{"qa.read"}, retrieval.DeleteSearchHistory)

	// ----- DatabaseService (RAG databases) -----
	handleAPI(r, "GET", "/api/v1/rag/database/tags", []string{"document.read"}, database.GetUserDatabaseTags)
	handleAPI(r, "POST", "/api/v1/rag/databases", []string{"document.read"}, database.GetUserDatabases)
	handleAPI(r, "POST", "/api/v1/rag/databases/create", []string{"document.write"}, database.CreateDatabase)
	handleAPI(r, "GET", "/api/v1/rag/databases/summary", []string{"document.read"}, database.GetUserDatabaseSummaries)
	handleAPI(r, "POST", "/api/v1/rag/databases/validate-connection", []string{"document.write"}, database.ValidateConnection)
	handleAPI(r, "DELETE", "/api/v1/rag/databases/{database_id}", []string{"document.write"}, database.DeleteDatabase)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables", []string{"document.read"}, database.GetDatabaseTables)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/cell", []string{"document.write"}, database.UpdateTableCell)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/preview", []string{"document.read"}, database.ListTableRows)
	handleAPI(r, "POST", "/api/v1/rag/databases/{database_id}/update", []string{"document.write"}, database.UpdateDatabase)

	// ----- Internal -----
	handleAPI(r, "GET", "/api/v1/inner/datasets/{dataset}:internal", []string{"document.read"}, inner.GetDataset)
	handleAPI(r, "POST", "/api/v1/inner/rag:knowledgeRetrieve", []string{"qa.read"}, inner.KnowledgeRetrieve)

	// ----- WriterSegmentJob -----
	handleAPI(r, "POST", "/api/v1/writerSegmentJob:submit", []string{"document.write"}, writersegmentjob.Submit)
	handleAPI(r, "GET", "/api/v1/writerSegmentJobs/{writerSegmentJob}", []string{"document.read"}, writersegmentjob.Get)
}
