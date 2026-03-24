// Package main 提供 Core API 的 Swagger 注解，由 swag init 生成 docs，请勿直接调用本文件中的函数。
package main

// Swagger 通用信息（swag init 会扫描）
// @title           Backend Core API
// @version         0.1.0
// @description     LazyRAG Go backend core API - proxies to algorithm services. 经 Kong 暴露时前缀为 /api/core。
// @BasePath        /api/core
// @schemes         http https
func _swagGeneral() {}

// --- health & misc ---
// @Summary  Health check
// @Router   /health [get]
func _swagHealth() {}

// @Summary  Hello (requires user.read)
// @Router   /hello [get]
func _swagHello() {}

// @Summary  Admin (requires document.write)
// @Router   /admin [get]
func _swagAdmin() {}

// --- dataset ---
// @Summary  数据集算法列表
// @Tags      dataset
// @Router    /dataset/algos [get]
func _swagListAlgos() {}

// @Summary  数据集标签
// @Tags      dataset
// @Router    /dataset/tags [get]
func _swagDatasetTags() {}

// @Summary  数据集列表
// @Tags      datasets
// @Router    /datasets [get]
func _swagListDatasets() {}

// @Summary  创建数据集
// @Tags      datasets
// @Router    /datasets [post]
func _swagCreateDataset() {}

// @Summary  获取数据集
// @Tags      datasets
// @Router    /datasets/{dataset} [get]
func _swagGetDataset() {}

// @Summary  删除数据集
// @Tags      datasets
// @Router    /datasets/{dataset} [delete]
func _swagDeleteDataset() {}

// @Summary  更新数据集
// @Tags      datasets
// @Router    /datasets/{dataset} [patch]
func _swagUpdateDataset() {}

// @Summary  设为默认数据集
// @Tags      datasets
// @Router    /datasets/{dataset}:setDefault [post]
func _swagSetDefault() {}

// @Summary  取消默认数据集
// @Tags      datasets
// @Router    /datasets/{dataset}:unsetDefault [post]
func _swagUnsetDefault() {}

// @Summary  全部默认数据集
// @Tags      datasets
// @Router    /datasets:allDefaultDatasets [get]
func _swagAllDefaultDatasets() {}

// @Summary  预签封面上传 URL
// @Tags      datasets
// @Router    /datasets:presignUploadCoverImageUrl [post]
func _swagPresignUploadCoverImageURL() {}

// @Summary  搜索数据集
// @Tags      datasets
// @Router    /datasets:search [post]
func _swagSearchDatasets() {}

// @Summary  数据集任务回调
// @Tags      datasets
// @Router    /datasets/{dataset}/tasks:callback [post]
func _swagCallbackTask() {}

// --- documents ---
// @Summary  文档列表
// @Tags      documents
// @Router    /datasets/{dataset}/documents [get]
func _swagListDocuments() {}

// @Summary  创建文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents [post]
func _swagCreateDocument() {}

// @Summary  获取文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents/{document} [get]
func _swagGetDocument() {}

// @Summary  预览文档内容
// @Tags      documents
// @Router    /datasets/{dataset}/documents/{document}:content [get]
func _swagGetDocumentContent() {}

// @Summary  下载文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents/{document}:download [get]
func _swagDownloadDocument() {}

// @Summary  删除文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents/{document} [delete]
func _swagDeleteDocument() {}

// @Summary  更新文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents/{document} [patch]
func _swagUpdateDocument() {}

// @Summary  搜索文档
// @Tags      documents
// @Router    /datasets/{dataset}/documents:search [post]
func _swagSearchDocuments() {}

// @Summary  全局搜索文档
// @Tags      documents
// @Router    /documents:search [post]
func _swagSearchAllDocuments() {}

// @Summary  批量删除
// @Tags      datasets
// @Router    /datasets/{dataset}:batchDelete [post]
func _swagBatchDelete() {}

// @Summary  文档创建者列表
// @Tags      document
// @Router    /document/creators [get]
func _swagDocumentCreators() {}

// @Summary  文档标签
// @Tags      document
// @Router    /document/tags [get]
func _swagDocumentTags() {}

// @Summary  表格添加数据
// @Tags      table
// @Router    /datasets/{dataset}/documents/{document}/table:add [post]
func _swagAddTableData() {}

// @Summary  表格批量删除
// @Tags      table
// @Router    /datasets/{dataset}/documents/{document}/table:batchDelete [post]
func _swagBatchDeleteTableData() {}

// @Summary  表格修改
// @Tags      table
// @Router    /datasets/{dataset}/documents/{document}/table:modify [post]
func _swagModifyTableData() {}

// @Summary  表格搜索
// @Tags      table
// @Router    /datasets/{dataset}/documents/{document}/table:search [get]
func _swagSearchTableData() {}

// --- segments ---
// @Summary  分段列表
// @Tags      segments
// @Router    /datasets/{dataset}/documents/{document}/segments [get]
func _swagListSegments() {}

// @Summary  获取分段
// @Tags      segments
// @Router    /datasets/{dataset}/documents/{document}/segments/{segment} [get]
func _swagGetSegment() {}

// @Summary  编辑分段
// @Tags      segments
// @Router    /datasets/{dataset}/documents/{document}/segments/{segment}:edit [post]
func _swagEditSegment() {}

// @Summary  修改分段状态
// @Tags      segments
// @Router    /datasets/{dataset}/documents/{document}/segments/{segment}:modifyStatus [post]
func _swagModifyStatus() {}

// @Summary  搜索分段
// @Tags      segments
// @Router    /datasets/{dataset}/documents/{document}/segments:search [post]
func _swagSearchSegments() {}

// @Summary  删除分段
// @Tags      segments
// @Router    /datasets/{dataset}/group/{group}/documents/{document}/segments/{segment} [delete]
func _swagDeleteSegment() {}

// @Summary  图片 URI 批量签名
// @Tags      segments
// @Router    /segment/imageURIs:batchSign [post]
func _swagBatchSignImageURI() {}

// @Summary  分段批量删除
// @Tags      segments
// @Router    /segments:bulkDelete [post]
func _swagBulkDelete() {}

// @Summary  分段混合搜索
// @Tags      segments
// @Router    /segments:hybrid [post]
func _swagHybridSearchSegments() {}

// @Summary  分段滚动
// @Tags      segments
// @Router    /segments:scroll [post]
func _swagScrollSegments() {}

// --- table ---
// @Summary  表格元数据
// @Tags      table
// @Router    /datasets/{dataset}/documents/{document}/table/meta [get]
func _swagGetMeta() {}

// @Summary  查找表格元数据
// @Tags      table
// @Router    /table:findMeta [post]
func _swagFindMeta() {}

// @Summary  表格查询
// @Tags      table
// @Router    /table:query [post]
func _swagQueryTable() {}

// --- members ---
// @Summary  数据集成员列表
// @Tags      members
// @Router    /datasets/{dataset}/members [get]
func _swagListDatasetMembers() {}

// @Summary  获取成员
// @Tags      members
// @Router    /datasets/{dataset}/members/{member} [get]
func _swagGetDatasetMember() {}

// @Summary  删除成员
// @Tags      members
// @Router    /datasets/{dataset}/members/{member} [delete]
func _swagDeleteDatasetMember() {}

// @Summary  更新成员
// @Tags      members
// @Router    /datasets/{dataset}/members/{member} [patch]
func _swagUpdateDatasetMember() {}

// @Summary  搜索成员
// @Tags      members
// @Router    /datasets/{dataset}/members:search [post]
func _swagSearchDatasetMember() {}

// @Summary  批量添加成员
// @Tags      members
// @Router    /datasets/{dataset}:batchAddMember [post]
func _swagBatchAddDatasetMember() {}

// --- tasks ---
// @Summary  任务列表
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks [get]
func _swagListTasks() {}

// @Summary  创建任务
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks [post]
func _swagCreateTask() {}

// @Summary  上传文件
// @Tags      tasks
// @Router    /datasets/{dataset}/uploads [post]
func _swagUploadDatasetFiles() {}

// @Summary  预览已上传文件
// @Tags      tasks
// @Router    /datasets/{dataset}/uploads/{upload_file_id}:content [get]
func _swagGetUploadedFileContent() {}

// @Summary  下载已上传文件
// @Tags      tasks
// @Router    /datasets/{dataset}/uploads/{upload_file_id}:download [get]
func _swagDownloadUploadedFile() {}

// @Summary  批量上传文件并创建任务
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks:batchUpload [post]
func _swagBatchUploadTasks() {}

// @Summary  获取任务
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks/{task} [get]
func _swagGetTask() {}

// @Summary  删除任务
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks/{task} [delete]
func _swagDeleteTask() {}

// @Summary  暂停任务
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks/{task}:suspend [post]
func _swagSuspendTask() {}

// @Summary  任务回调
// @Tags      tasks
// @Router    /datasets/{dataset}/tasks/{task}:callback [post]
func _swagTaskCallback() {}

// --- file ---
// @Summary  上传文件到知识库
// @Tags      file
// @Router    /upload_files [post]
func _swagUploadFiles() {}

// @Summary  上传并加入知识库分组
// @Tags      file
// @Router    /add_files_to_group [post]
func _swagAddFilesToGroup() {}

// @Summary  知识库文件列表
// @Tags      file
// @Router    /list_files [get]
func _swagListFiles() {}

// @Summary  分组内文件列表
// @Tags      file
// @Router    /list_files_in_group [get]
func _swagListFilesInGroup() {}

// @Summary  知识库分组列表
// @Tags      file
// @Router    /list_kb_groups [get]
func _swagListKBGroups() {}

// --- chat ---
// @Summary  对话（知识库）
// @Tags      chat
// @Router    /chat [post]
func _swagChat() {}

// --- conversations ---
// @Summary  会话对话
// @Tags      conversations
// @Router    /conversations:chat [post]
func _swagConversationsChat() {}

// @Summary  恢复对话流
// @Tags      conversations
// @Router    /conversations:resumeChat [post]
func _swagConversationsResumeChat() {}

// @Summary  停止对话生成
// @Tags      conversations
// @Router    /conversations:stopChatGeneration [post]
func _swagConversationsStopChatGeneration() {}

// @Summary  获取对话状态
// @Tags      conversations
// @Router    /conversations/{conversation_id}:status [get]
func _swagGetChatStatus() {}

// @Summary  获取会话
// @Tags      conversations
// @Router    /conversations/{name} [get]
func _swagGetConversation() {}

// @Summary  获取会话详情
// @Tags      conversations
// @Router    /conversations/{name}:detail [get]
func _swagGetConversationDetail() {}

// @Summary  删除会话
// @Tags      conversations
// @Router    /conversations/{name} [delete]
func _swagDeleteConversation() {}

// @Summary  会话列表
// @Tags      conversations
// @Router    /conversations [get]
func _swagListConversations() {}

// @Summary  设置会话历史
// @Tags      conversations
// @Router    /conversations:setChatHistory [post]
func _swagSetChatHistory() {}

// @Summary  反馈会话历史
// @Tags      conversations
// @Router    /conversations:feedBackChatHistory [post]
func _swagFeedBackChatHistory() {}

// @Summary  获取多答案开关状态
// @Tags      conversations
// @Router    /conversation:switchStatus [get]
func _swagGetMultiAnswersSwitchStatus() {}

// @Summary  设置多答案开关状态
// @Tags      conversations
// @Router    /conversation:switchStatus [post]
func _swagSetMultiAnswersSwitchStatus() {}

// --- prompts ---
// @Summary  创建提示词
// @Tags      prompts
// @Router    /prompts [post]
func _swagCreatePrompt() {}

// @Summary  更新提示词
// @Tags      prompts
// @Router    /prompts/{name} [patch]
func _swagUpdatePrompt() {}

// @Summary  删除提示词
// @Tags      prompts
// @Router    /prompts/{name} [delete]
func _swagDeletePrompt() {}

// @Summary  获取提示词
// @Tags      prompts
// @Router    /prompts/{name} [get]
func _swagGetPrompt() {}

// @Summary  提示词列表
// @Tags      prompts
// @Router    /prompts [get]
func _swagListPrompts() {}

// @Summary  设为默认提示词
// @Tags      prompts
// @Router    /prompts/{name}:setDefault [post]
func _swagSetDefaultPrompt() {}

// @Summary  取消默认提示词
// @Tags      prompts
// @Router    /prompts/{name}:unsetDefault [post]
func _swagUnsetDefaultPrompt() {}

// --- rag databases ---
// @Summary  RAG 数据库标签
// @Tags      rag
// @Router    /rag/database/tags [get]
func _swagGetUserDatabaseTags() {}

// @Summary  用户数据库列表
// @Tags      rag
// @Router    /rag/databases [post]
func _swagGetUserDatabases() {}

// @Summary  创建数据库
// @Tags      rag
// @Router    /rag/databases/create [post]
func _swagCreateDatabase() {}

// @Summary  数据库摘要
// @Tags      rag
// @Router    /rag/databases/summary [get]
func _swagGetUserDatabaseSummaries() {}

// @Summary  验证连接
// @Tags      rag
// @Router    /rag/databases/validate-connection [post]
func _swagValidateConnection() {}

// @Summary  删除数据库
// @Tags      rag
// @Router    /rag/databases/{database_id} [delete]
func _swagDeleteDatabase() {}

// @Summary  数据库表列表
// @Tags      rag
// @Router    /rag/databases/{database_id}/tables [post]
func _swagGetDatabaseTables() {}

// @Summary  更新单元格
// @Tags      rag
// @Router    /rag/databases/{database_id}/tables/{table_id}/cell [post]
func _swagUpdateTableCell() {}

// @Summary  表行预览
// @Tags      rag
// @Router    /rag/databases/{database_id}/tables/{table_id}/preview [post]
func _swagListTableRows() {}

// @Summary  更新数据库
// @Tags      rag
// @Router    /rag/databases/{database_id}/update [post]
func _swagUpdateDatabase() {}

// --- inner ---
// @Summary  内部获取数据集
// @Tags      inner
// @Router    /inner/datasets/{dataset}:internal [get]
func _swagGetDatasetInternal() {}

// @Summary  知识检索
// @Tags      inner
// @Router    /inner/rag:knowledgeRetrieve [post]
func _swagKnowledgeRetrieve() {}

// --- writer segment job ---
// @Summary  提交 WriterSegmentJob
// @Tags      job
// @Router    /writerSegmentJob:submit [post]
func _swagSubmit() {}

// @Summary  获取 WriterSegmentJob
// @Tags      job
// @Router    /writerSegmentJobs/{writerSegmentJob} [get]
func _swagGetWriterSegmentJob() {}

// --- kb acl ---
// @Summary  知识库列表
// @Tags      kb
// @Router    /kb/list [get]
func _swagListKB() {}

// @Summary  权限批量查询
// @Tags      kb
// @Router    /kb/permission/batch [post]
func _swagPermissionBatch() {}

// @Summary  知识库权限
// @Tags      kb
// @Router    /kb/{kb_id}/permission [get]
func _swagGetPermission() {}

// @Summary  权限校验
// @Tags      kb
// @Router    /kb/{kb_id}/can [get]
func _swagCanHandler() {}

// @Summary  ACL 列表
// @Tags      kb
// @Router    /kb/{kb_id}/acl [get]
func _swagListACL() {}

// @Summary  添加 ACL
// @Tags      kb
// @Router    /kb/{kb_id}/acl [post]
func _swagAddACL() {}

// @Summary  批量添加 ACL
// @Tags      kb
// @Router    /kb/{kb_id}/acl/batch [post]
func _swagBatchAddACL() {}

// @Summary  更新 ACL
// @Tags      kb
// @Router    /kb/{kb_id}/acl/{acl_id} [put]
func _swagUpdateACL() {}

// @Summary  删除 ACL
// @Tags      kb
// @Router    /kb/{kb_id}/acl/{acl_id} [delete]
func _swagDeleteACL() {}
