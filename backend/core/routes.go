package main

import (
	"net/http"

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
func registerAllRoutes(mux *http.ServeMux) {
	// ----- DatasetService -----
	handleAPI(mux, "GET", "/api/v1/dataset/algos", []string{"document.read"}, dataset.ListAlgos)
	handleAPI(mux, "GET", "/api/v1/dataset/tags", []string{"document.read"}, dataset.AllDatasetTags)
	handleAPI(mux, "GET", "/api/v1/datasets", []string{"document.read"}, dataset.ListDatasets)
	handleAPI(mux, "POST", "/api/v1/datasets", []string{"document.write"}, dataset.CreateDataset)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}", []string{"document.read"}, dataset.GetDataset)
	handleAPI(mux, "DELETE", "/api/v1/datasets/{dataset}", []string{"document.write"}, dataset.DeleteDataset)
	handleAPI(mux, "PATCH", "/api/v1/datasets/{dataset}", []string{"document.write"}, dataset.UpdateDataset)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}:setDefault", []string{"document.write"}, dataset.SetDefault)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}:unsetDefault", []string{"document.write"}, dataset.UnsetDefault)
	handleAPI(mux, "GET", "/api/v1/datasets:allDefaultDatasets", []string{"document.read"}, dataset.AllDefaultDatasets)
	handleAPI(mux, "POST", "/api/v1/datasets:presignUploadCoverImageUrl", []string{"document.write"}, dataset.PresignUploadCoverImageURL)
	handleAPI(mux, "POST", "/api/v1/datasets:search", []string{"document.read"}, dataset.SearchDatasets)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks:callback", []string{"document.write"}, dataset.CallbackTask)

	// ----- DocumentService -----
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents", []string{"document.read"}, document.ListDocuments)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents", []string{"document.write"}, document.CreateDocument)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.read"}, document.GetDocument)
	handleAPI(mux, "DELETE", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, document.DeleteDocument)
	handleAPI(mux, "PATCH", "/api/v1/datasets/{dataset}/documents/{document}", []string{"document.write"}, document.UpdateDocument)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents:search", []string{"document.read"}, document.SearchDocuments)
	handleAPI(mux, "POST", "/api/v1/documents:search", []string{"document.read"}, document.SearchAllDocuments)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}:batchDelete", []string{"document.write"}, document.BatchDeleteDocument)
	handleAPI(mux, "GET", "/api/v1/document/creators", []string{"document.read"}, document.AllDocumentCreators)
	handleAPI(mux, "GET", "/api/v1/document/tags", []string{"document.read"}, document.AllDocumentTags)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:add", []string{"document.write"}, document.AddTableData)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:batchDelete", []string{"document.write"}, document.BatchDeleteTableData)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/table:modify", []string{"document.write"}, document.ModifyTableData)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table:search", []string{"document.read"}, document.SearchTableData)

	// ----- SegmentService -----
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments", []string{"document.read"}, segment.ListSegments)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}", []string{"document.read"}, segment.GetSegment)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:edit", []string{"document.write"}, segment.EditSegment)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments/{segment}:modifyStatus", []string{"document.write"}, segment.ModifyStatus)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/documents/{document}/segments:search", []string{"document.read"}, segment.SearchSegments)
	handleAPI(mux, "DELETE", "/api/v1/datasets/{dataset}/group/{group}/documents/{document}/segments/{segment}", []string{"document.write"}, segment.DeleteSegment)
	handleAPI(mux, "POST", "/api/v1/segment/imageURIs:batchSign", []string{"document.read"}, segment.BatchSignImageURI)
	handleAPI(mux, "POST", "/api/v1/segments:bulkDelete", []string{"document.write"}, segment.BulkDelete)
	handleAPI(mux, "POST", "/api/v1/segments:hybrid", []string{"document.read"}, segment.HybridSearchSegments)
	handleAPI(mux, "POST", "/api/v1/segments:scroll", []string{"document.read"}, segment.ScrollSegments)

	// ----- TableService -----
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/documents/{document}/table/meta", []string{"document.read"}, table.GetMeta)
	handleAPI(mux, "POST", "/api/v1/table:findMeta", []string{"document.read"}, table.FindMeta)
	handleAPI(mux, "POST", "/api/v1/table:query", []string{"document.read"}, table.QueryTable)

	// ----- DatasetMemberService -----
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/members", []string{"document.read"}, member.ListDatasetMembers)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.read"}, member.GetDatasetMember)
	handleAPI(mux, "DELETE", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, member.DeleteDatasetMember)
	handleAPI(mux, "PATCH", "/api/v1/datasets/{dataset}/members/{member}", []string{"document.write"}, member.UpdateDatasetMember)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/members:search", []string{"document.read"}, member.SearchDatasetMember)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}:batchAddMember", []string{"document.write"}, member.BatchAddDatasetMember)

	// ----- TaskService（直接暴露 Task，不再通过 Job）-----
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/tasks", []string{"document.read"}, task.ListTasks)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks", []string{"document.write"}, task.CreateTask)
	handleAPI(mux, "GET", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.read"}, task.GetTask)
	handleAPI(mux, "DELETE", "/api/v1/datasets/{dataset}/tasks/{task}", []string{"document.write"}, task.DeleteTask)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:cancel", []string{"document.write"}, task.CancelTask)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:suspend", []string{"document.write"}, task.SuspendTask)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:resume", []string{"document.write"}, task.ResumeTask)
	handleAPI(mux, "POST", "/api/v1/datasets/{dataset}/tasks/{task}:callback", []string{"document.write"}, task.CallbackTask)

	// ----- RetrievalService (search / QA) -----
	handleAPI(mux, "GET", "/api/v1/search:allSearchHistory", []string{"qa.read"}, retrieval.AllSearchHistory)
	handleAPI(mux, "POST", "/api/v1/search:searchKnowledge", []string{"qa.read"}, retrieval.SearchKnowledge)
	handleAPI(mux, "DELETE", "/api/v1/searchHistories/{searchHistory}", []string{"qa.read"}, retrieval.DeleteSearchHistory)

	// ----- DatabaseService (RAG databases) -----
	handleAPI(mux, "GET", "/api/v1/rag/database/tags", []string{"document.read"}, database.GetUserDatabaseTags)
	handleAPI(mux, "POST", "/api/v1/rag/databases", []string{"document.read"}, database.GetUserDatabases)
	handleAPI(mux, "POST", "/api/v1/rag/databases/create", []string{"document.write"}, database.CreateDatabase)
	handleAPI(mux, "GET", "/api/v1/rag/databases/summary", []string{"document.read"}, database.GetUserDatabaseSummaries)
	handleAPI(mux, "POST", "/api/v1/rag/databases/validate-connection", []string{"document.write"}, database.ValidateConnection)
	handleAPI(mux, "DELETE", "/api/v1/rag/databases/{database_id}", []string{"document.write"}, database.DeleteDatabase)
	handleAPI(mux, "POST", "/api/v1/rag/databases/{database_id}/tables", []string{"document.read"}, database.GetDatabaseTables)
	handleAPI(mux, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/cell", []string{"document.write"}, database.UpdateTableCell)
	handleAPI(mux, "POST", "/api/v1/rag/databases/{database_id}/tables/{table_id}/preview", []string{"document.read"}, database.ListTableRows)
	handleAPI(mux, "POST", "/api/v1/rag/databases/{database_id}/update", []string{"document.write"}, database.UpdateDatabase)

	// ----- Internal -----
	handleAPI(mux, "GET", "/api/v1/inner/datasets/{dataset}:internal", []string{"document.read"}, inner.GetDataset)
	handleAPI(mux, "POST", "/api/v1/inner/rag:knowledgeRetrieve", []string{"qa.read"}, inner.KnowledgeRetrieve)

	// ----- WriterSegmentJob -----
	handleAPI(mux, "POST", "/api/v1/writerSegmentJob:submit", []string{"document.write"}, writersegmentjob.Submit)
	handleAPI(mux, "GET", "/api/v1/writerSegmentJobs/{writerSegmentJob}", []string{"document.read"}, writersegmentjob.Get)
}
