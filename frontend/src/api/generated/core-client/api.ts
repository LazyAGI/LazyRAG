/* tslint:disable */
/* eslint-disable */



import type { Configuration } from './configuration';
import type { AxiosPromise, AxiosInstance, RawAxiosRequestConfig } from 'axios';
import globalAxios from 'axios';
// Some imports not used depending on template conditions
// @ts-ignore
import { DUMMY_BASE_URL, assertParamExists, setApiKeyToObject, setBasicAuthToObject, setBearerAuthToObject, setOAuthToObject, setSearchParams, serializeDataIfNeeded, toPathString, createRequestFunction, replaceWithSerializableTypeIfNeeded } from './common';
import type { RequestArgs } from './base';
// @ts-ignore
import { BASE_PATH, COLLECTION_FORMATS, BaseAPI, RequiredError, operationServerMap } from './base';

export interface ACLApiResponse {
    'code'?: number;
    'data'?: object;
    'message'?: string;
}
export interface ACLListData {
    'list'?: Array<ACLListItem>;
}
export interface ACLListItem {
    'created_at'?: string;
    'grantee_id'?: string;
    'grantee_type'?: string;
    'id'?: number;
    'permission'?: string;
}
export interface AbortUploadRequest {
    'reason'?: string;
}
export interface AbortUploadResponse {
    'upload_id'?: string;
    'upload_state'?: string;
}
export interface AddACLData {
    'acl_id'?: number;
}
export interface AddACLRequest {
    'expires_at'?: string;
    'grantee_id': string;
    'grantee_type': string;
    'permission': string;
}
export interface Algo {
    'algo_id': string;
    'description': string;
    'display_name': string;
}
export interface AllDatasetTagsResponse {
    'tags'?: Array<string>;
}
export interface ApiCoreChatPostRequest {
    'files'?: Array<string>;
    'filters'?: object;
    'history'?: Array<string>;
    'query'?: string;
    'session_id'?: string;
}
export interface ApiCoreChatStreamPostRequest {
    'history'?: Array<string>;
    'query'?: string;
    'session_id'?: string;
}
export interface ApiCoreKbGrantPrincipalsGet200Response {
    'code'?: number;
    'data'?: ListGrantPrincipalsResponse;
    'message'?: string;
}
export interface ApiCoreKbKbIdAclAclIdPut200Response {
    'code'?: number;
    'data'?: object;
    'message'?: string;
}
export interface ApiCoreKbKbIdAclBatchPost200Response {
    'code'?: number;
    'data'?: BatchAddACLData;
    'message'?: string;
}
export interface ApiCoreKbKbIdAclGet200Response {
    'code'?: number;
    'data'?: ACLListData;
    'message'?: string;
}
export interface ApiCoreKbKbIdAclPost200Response {
    'code'?: number;
    'data'?: AddACLData;
    'message'?: string;
}
export interface ApiCoreKbKbIdAuthorizationGet200Response {
    'code'?: number;
    'data'?: GetKBAuthorizationResponse;
    'message'?: string;
}
export interface ApiCoreKbKbIdAuthorizationPost200Response {
    'code'?: number;
    'data'?: SetKBAuthorizationData;
    'message'?: string;
}
export interface ApiCoreKbKbIdCanGet200Response {
    'code'?: number;
    'data'?: CanResult;
    'message'?: string;
}
export interface ApiCoreKbKbIdPermissionGet200Response {
    'code'?: number;
    'data'?: PermissionResult;
    'message'?: string;
}
export interface ApiCoreKbListGet200Response {
    'code'?: number;
    'data'?: KBListResult;
    'message'?: string;
}
export interface ApiCoreKbPermissionBatchPost200Response {
    'code'?: number;
    'data'?: Array<PermissionBatchItem>;
    'message'?: string;
}
export interface AuthorizationSubjectGrant {
    'grantee_id'?: string;
    'grantee_type'?: string;
    'permissions'?: Array<string>;
}
export interface BatchAddACLData {
    'count'?: number;
    'failed_count'?: number;
    'invalid_count'?: number;
}
export interface BatchAddACLItem {
    'grantee_id': string;
    'grantee_type': string;
    'permission': string;
}
export interface BatchAddACLRequest {
    'items': Array<BatchAddACLItem>;
}
export interface BatchAddDatasetMemberRequest {
    'group_id_list'?: Array<string>;
    'group_name_list'?: Array<string>;
    'parent'?: string;
    'role'?: BatchAddDatasetMemberRequestRole;
    'user_id_list'?: Array<string>;
    'user_name_list'?: Array<string>;
}
export interface BatchAddDatasetMemberRequestRole {
    'role'?: string;
}
export interface BatchAddDatasetMemberResponse {
    'dataset_members'?: Array<DatasetMember>;
}
export interface BatchDeleteDocumentRequest {
    'names'?: Array<string>;
    'parent': string;
}
export interface BatchUploadTasksResponse {
    'tasks'?: Array<TaskResponse>;
}
export interface CanResult {
    'allowed'?: boolean;
}
export interface ChatChunkResponse {
    'conversation_id'?: string;
    'delta'?: string;
    'finish_reason'?: string;
    'history_id'?: string;
    'message'?: string;
    'prompt_questions'?: Array<string>;
    'reasoning_content'?: string;
    'seq'?: number;
    'sources'?: Array<object>;
    'thinking_duration_s'?: number;
}
export interface CompleteUploadRequest {
    'auto_start'?: boolean;
    'idempotency_key'?: string;
}
export interface CompleteUploadResponse {
    'content_url'?: string;
    'convert_error'?: string;
    'convert_status'?: string;
    'dataset_id'?: string;
    'document_id'?: string;
    'download_url'?: string;
    'file_size'?: number;
    'file_url'?: string;
    'parse_stored_path'?: string;
    'stored_path': string;
    'task_id'?: string;
    'upload_file_id'?: string;
    'upload_id': string;
    'upload_scope'?: string;
}
export interface ConversationChatStatusResponse {
    'is_generating'?: boolean;
}
export interface ConversationDetailResponse {
    'conversation'?: ConversationItem;
    'history'?: Array<ConversationHistoryItem>;
}
export interface ConversationFeedbackRequest {
    'expected_answer'?: string;
    'history_id': string;
    'reason'?: string;
    'type': number;
}
export interface ConversationHistoryItem {
    'create_time'?: string;
    'expected_answer'?: string;
    'feed_back'?: number;
    'id'?: string;
    'input'?: object;
    'query'?: string;
    'reason'?: string;
    'reasoning_content'?: string;
    'result'?: string;
    'seq'?: number;
    'sources'?: Array<object>;
}
export interface ConversationItem {
    'chat_times'?: number;
    'conversation_id'?: string;
    'create_time'?: string;
    'display_name'?: string;
    'models'?: Array<string>;
    'name'?: string;
    'search_config'?: object;
    'total_feedback_like'?: number;
    'total_feedback_unlike'?: number;
    'update_time'?: string;
    'user'?: string;
}
export interface ConversationListResponse {
    'conversations'?: Array<ConversationItem>;
    'next_page_token'?: string;
    'total_size'?: number;
}
export interface ConversationResumeRequest {
    'conversation_id': string;
    'history_id'?: string;
}
export interface ConversationSetHistoryRequest {
    'deleted_history_id': string;
    'set_history_id': string;
}
export interface ConversationStopRequest {
    'conversation_id': string;
    'history_id'?: string;
}
export interface ConversationSwitchStatusRequest {
    'status': number;
}
export interface ConversationSwitchStatusResponse {
    'status'?: number;
}
export interface CreateTaskItem {
    'cross_dataset'?: boolean;
    'task': TaskPayload;
    'task_id'?: string;
    'upload_file_id'?: string;
}
export interface CreateTaskRequest {
    'items': Array<CreateTaskItem>;
    'parent'?: string;
}
export interface CreateTasksResponse {
    'tasks'?: Array<TaskResponse>;
}
export interface Dataset {
    'acl'?: Array<string>;
    'algo': Algo;
    'cover_image': string;
    'create_time': string;
    'creator': string;
    'dataset_id': string;
    'default_dataset': boolean;
    'desc': string;
    'display_name': string;
    'document_count': number;
    'document_size': number;
    'is_empty': boolean;
    'name': string;
    'parsers'?: Array<ParserConfig>;
    'segment_count': number;
    'share_type': string;
    'state': string;
    'tags'?: Array<string>;
    'token_count': number;
    'type': string;
    'update_time': string;
}
export interface DatasetMember {
    'create_time'?: string;
    'dataset_id'?: string;
    'group'?: string;
    'group_id'?: string;
    'name'?: string;
    'role'?: DatasetRole;
    'user'?: string;
    'user_id'?: string;
}
export interface DatasetRole {
    'display_name'?: string;
    'role'?: string;
}
export interface Doc {
    'child_document_count'?: number;
    'child_folder_count'?: number;
    'children'?: Array<Doc>;
    'columns'?: Array<DocumentTableColumn>;
    'convert_file_uri': string;
    'create_time': string;
    'creator': string;
    'data_source_type': string;
    'dataset_display': string;
    'dataset_id': string;
    'display_name': string;
    'document_id': string;
    'document_size': number;
    'document_stage': string;
    'download_file_url'?: string;
    'file_id': string;
    'file_system_path': string;
    'file_url'?: string;
    'name': string;
    'p_id': string;
    'pdf_convert_result'?: string;
    'recursive_document_count'?: number;
    'recursive_file_size'?: number;
    'recursive_folder_count'?: number;
    'rel_path': string;
    'tags'?: Array<string>;
    'type': string;
    'update_time': string;
    'uri': string;
}
export interface DocumentCreatorsResponse {
    'creators'?: Array<UserInfo>;
}
export interface DocumentTableColumn {
    'desc': string;
    'display_name': string;
    'id': number;
    'index_type': string;
    'sample': string;
    'source_column': string;
    'type': string;
}
export interface DocumentTagsResponse {
    'tags'?: Array<string>;
}
export interface ErrorResponse {
    'code'?: number;
    'message'?: string;
}
export interface GetKBAuthorizationResponse {
    'grants'?: Array<AuthorizationSubjectGrant>;
    'kb_id'?: string;
}
export interface GrantPrincipal {
    'grantee_id'?: string;
    'grantee_type'?: string;
    'name'?: string;
}
export interface InitUploadRequest {
    'content_type'?: string;
    'document_pid'?: string;
    'file_size'?: number;
    'filename': string;
    'idempotency_key'?: string;
    'part_size'?: number;
    'relative_path'?: string;
}
export interface InitUploadResponse {
    'dataset_id'?: string;
    'document_id'?: string;
    'part_size'?: number;
    'stored_name': string;
    'task_id'?: string;
    'total_parts'?: number;
    'upload_id': string;
    'upload_mode': string;
    'upload_scope'?: string;
    'upload_state': string;
}
export interface KBListResult {
    'list'?: Array<KBListRow>;
    'total'?: number;
}
export interface KBListRow {
    'id'?: string;
    'name'?: string;
    'permissions'?: Array<string>;
    'visibility'?: string;
}
export interface ListAlgosResponse {
    'algos'?: Array<Algo>;
}
export interface ListDatasetMembersResponse {
    'dataset_members'?: Array<DatasetMember>;
    'next_page_token'?: string;
}
export interface ListDatasetsResponse {
    'datasets'?: Array<Dataset>;
    'next_page_token': string;
    'total_size': number;
}
export interface ListDocumentsResponse {
    'documents'?: Array<Doc>;
    'next_page_token'?: string;
    'total_size'?: number;
}
export interface ListGrantPrincipalsResponse {
    'groups'?: Array<GrantPrincipal>;
    'users'?: Array<GrantPrincipal>;
}
export interface ListTasksResponse {
    'next_page_token'?: string;
    'tasks'?: Array<TaskResponse>;
    'total_size'?: number;
}
export interface ParserConfig {
    'name': string;
    'params'?: { [key: string]: object; };
    'type': string;
}
export interface PermissionBatchItem {
    'kb_id'?: string;
    'permissions'?: Array<string>;
}
export interface PermissionBatchRequest {
    'kb_ids': Array<string>;
}
export interface PermissionResult {
    'permissions'?: Array<string>;
    'source'?: string;
}
export interface PromptItem {
    'content'?: string;
    'display_name'?: string;
    'id'?: string;
    'is_default'?: boolean;
    'name'?: string;
}
export interface PromptListResponse {
    'next_page_token'?: string;
    'prompts'?: Array<PromptItem>;
    'total'?: number;
}
export interface PromptPatchRequest {
    'content'?: string;
    'display_name'?: string;
}
export interface PromptRequest {
    'content': string;
    'display_name': string;
}
export interface ResumeTaskRequest {
    'task_id'?: string;
}
export interface SearchDatasetMemberRequest {
    'is_all'?: boolean;
    'name_prefix'?: string;
    'page_size'?: number;
    'page_token'?: string;
    'parent'?: string;
}
export interface SearchDocumentsRequest {
    'dir_path'?: string;
    'keyword'?: string;
    'order_by'?: string;
    'p_id'?: string;
    'page_size'?: number;
    'page_token'?: string;
    'parent'?: string;
    'recursive'?: boolean;
}
export interface SearchTasksRequest {
    'task_ids': Array<string>;
    'task_state'?: string;
}
export interface SetChatHistoryResponse {
    'history_id'?: string;
}
export interface SetDefaultDatasetRequest {
    'name': string;
}
export interface SetKBAuthorizationData {
    'acl_rows'?: number;
    'kb_id'?: string;
    'subject_count'?: number;
}
export interface SetKBAuthorizationRequest {
    'grants'?: Array<AuthorizationSubjectGrant>;
}
export interface StartTaskRequest {
    'start_mode'?: string;
    'task_ids': Array<string>;
}
export interface StartTaskResult {
    'display_name'?: string;
    'document_id'?: string;
    'message'?: string;
    'status': string;
    'submit_status'?: string;
    'task_id': string;
}
export interface StartTasksResponse {
    'failed_count': number;
    'requested_count': number;
    'started_count': number;
    'tasks'?: Array<StartTaskResult>;
}
export interface SuspendJobRequest {
    'task_id'?: string;
}
export interface TaskDocumentInfo {
    'display_name'?: string;
    'document_id'?: string;
    'document_size'?: number;
    'document_state'?: string;
}
export interface TaskFile {
    'content_type'?: string;
    'display_name'?: string;
    'file_size'?: number;
    'parse_stored_path'?: string;
    'relative_path'?: string;
    'stored_name'?: string;
    'stored_path'?: string;
}
export interface TaskInfo {
    'failed_document_count'?: number;
    'failed_document_size'?: number;
    'filtered_document_count'?: number;
    'succeed_document_count'?: number;
    'succeed_document_size'?: number;
    'succeed_token_count'?: number;
    'total_document_count'?: number;
    'total_document_size'?: number;
}
export interface TaskPayload {
    'data_source_type'?: string;
    'display_name'?: string;
    'document_id'?: string;
    'document_ids'?: Array<string>;
    'document_pid'?: string;
    'document_tags'?: Array<string>;
    'files'?: Array<TaskFile>;
    'reparse_groups'?: Array<string>;
    'target_dataset_id'?: string;
    'target_path'?: string;
    'target_pid'?: string;
    'task_type'?: string;
}
export interface TaskResponse {
    'convert_error'?: string;
    'convert_required'?: boolean;
    'convert_status'?: string;
    'create_time'?: string;
    'creator'?: string;
    'data_source_type'?: string;
    'display_name'?: string;
    'document_id'?: string;
    'document_info'?: Array<TaskDocumentInfo>;
    'err_msg'?: string;
    'files'?: Array<TaskFile>;
    'finish_time'?: string;
    'name'?: string;
    'parse_stored_path'?: string;
    'pdf_convert_result'?: string;
    'start_time'?: string;
    'target_dataset_id'?: string;
    'target_pid'?: string;
    'task_id'?: string;
    'task_info'?: TaskInfo;
    'task_state': string;
    'task_type'?: string;
}
export interface TransferBinding {
    'display_name'?: string;
    'error_message'?: string;
    'mode'?: string;
    'source_document_id'?: string;
    'source_lazy_doc_id'?: string;
    'status'?: string;
    'stored_path'?: string;
    'target_document_id'?: string;
    'target_lazy_doc_id'?: string;
}
export interface UnsetDefaultDatasetRequest {
    'name': string;
}
export interface UpdateACLRequest {
    'expires_at'?: string;
    'permission': string;
}
export interface UpdateDatasetMemberRequest {
    'dataset_member'?: DatasetMember;
    'update_mask'?: UpdateDatasetMemberRequestUpdateMask;
}
export interface UpdateDatasetMemberRequestUpdateMask {
    'paths'?: Array<string>;
}
export interface UploadFileResponse {
    'content_type'?: string;
    'content_url'?: string;
    'dataset_id'?: string;
    'document_pid'?: string;
    'document_tags'?: Array<string>;
    'download_url'?: string;
    'file_size'?: number;
    'file_url'?: string;
    'filename'?: string;
    'relative_path'?: string;
    'status'?: string;
    'stored_name'?: string;
    'stored_path'?: string;
    'upload_file_id'?: string;
    'upload_scope'?: string;
}
export interface UploadFilesResponse {
    'files'?: Array<UploadFileResponse>;
}
export interface UploadPartResponse {
    'part_number'?: number;
    'part_size'?: number;
    'total_parts'?: number;
    'upload_id'?: string;
    'upload_state'?: string;
    'uploaded_parts'?: number;
}
export interface UserInfo {
    'display_name'?: string;
}

/**
 * DatasetsApi - axios parameter creator
 */
export const DatasetsApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        apiCoreDatasetsDatasetDelete: async (dataset: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDelete', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetGet: async (dataset: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetGet', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetPatch: async (dataset: string, dataset2?: Dataset, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetPatch', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(dataset2, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetSetDefaultPost: async (dataset: string, setDefaultDatasetRequest: SetDefaultDatasetRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetSetDefaultPost', 'dataset', dataset)
            // verify required parameter 'setDefaultDatasetRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetSetDefaultPost', 'setDefaultDatasetRequest', setDefaultDatasetRequest)
            const localVarPath = `/api/core/datasets/{dataset}:setDefault`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(setDefaultDatasetRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUnsetDefaultPost: async (dataset: string, unsetDefaultDatasetRequest: UnsetDefaultDatasetRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUnsetDefaultPost', 'dataset', dataset)
            // verify required parameter 'unsetDefaultDatasetRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUnsetDefaultPost', 'unsetDefaultDatasetRequest', unsetDefaultDatasetRequest)
            const localVarPath = `/api/core/datasets/{dataset}:unsetDefault`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(unsetDefaultDatasetRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsGet: async (pageToken?: string, pageSize?: number, orderBy?: string, keyword?: string, tags?: Array<string>, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/datasets`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (pageToken !== undefined) {
                localVarQueryParameter['page_token'] = pageToken;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (orderBy !== undefined) {
                localVarQueryParameter['order_by'] = orderBy;
            }

            if (keyword !== undefined) {
                localVarQueryParameter['keyword'] = keyword;
            }

            if (tags) {
                localVarQueryParameter['tags'] = tags;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsPost: async (datasetId?: string, dataset?: Dataset, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/datasets`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (datasetId !== undefined) {
                localVarQueryParameter['dataset_id'] = datasetId;
            }

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(dataset, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * DatasetsApi - functional programming interface
 */
export const DatasetsApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = DatasetsApiAxiosParamCreator(configuration)
    return {
        
        async apiCoreDatasetsDatasetDelete(dataset: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDelete(dataset, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsDatasetDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetGet(dataset: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Dataset>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetGet(dataset, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsDatasetGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetPatch(dataset: string, dataset2?: Dataset, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Dataset>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetPatch(dataset, dataset2, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsDatasetPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetSetDefaultPost(dataset: string, setDefaultDatasetRequest: SetDefaultDatasetRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetSetDefaultPost(dataset, setDefaultDatasetRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsDatasetSetDefaultPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUnsetDefaultPost(dataset: string, unsetDefaultDatasetRequest: UnsetDefaultDatasetRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUnsetDefaultPost(dataset, unsetDefaultDatasetRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsDatasetUnsetDefaultPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsGet(pageToken?: string, pageSize?: number, orderBy?: string, keyword?: string, tags?: Array<string>, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDatasetsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsGet(pageToken, pageSize, orderBy, keyword, tags, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsPost(datasetId?: string, dataset?: Dataset, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Dataset>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsPost(datasetId, dataset, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DatasetsApi.apiCoreDatasetsPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * DatasetsApi - factory interface
 */
export const DatasetsApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = DatasetsApiFp(configuration)
    return {
        
        apiCoreDatasetsDatasetDelete(requestParameters: DatasetsApiApiCoreDatasetsDatasetDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetDelete(requestParameters.dataset, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetGet(requestParameters: DatasetsApiApiCoreDatasetsDatasetGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<Dataset> {
            return localVarFp.apiCoreDatasetsDatasetGet(requestParameters.dataset, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetPatch(requestParameters: DatasetsApiApiCoreDatasetsDatasetPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<Dataset> {
            return localVarFp.apiCoreDatasetsDatasetPatch(requestParameters.dataset, requestParameters.dataset2, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetSetDefaultPost(requestParameters: DatasetsApiApiCoreDatasetsDatasetSetDefaultPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetSetDefaultPost(requestParameters.dataset, requestParameters.setDefaultDatasetRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUnsetDefaultPost(requestParameters: DatasetsApiApiCoreDatasetsDatasetUnsetDefaultPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetUnsetDefaultPost(requestParameters.dataset, requestParameters.unsetDefaultDatasetRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsGet(requestParameters: DatasetsApiApiCoreDatasetsGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<ListDatasetsResponse> {
            return localVarFp.apiCoreDatasetsGet(requestParameters.pageToken, requestParameters.pageSize, requestParameters.orderBy, requestParameters.keyword, requestParameters.tags, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsPost(requestParameters: DatasetsApiApiCoreDatasetsPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<Dataset> {
            return localVarFp.apiCoreDatasetsPost(requestParameters.datasetId, requestParameters.dataset, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for apiCoreDatasetsDatasetDelete operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsDatasetDeleteRequest {
    readonly dataset: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetGet operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsDatasetGetRequest {
    readonly dataset: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetPatch operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsDatasetPatchRequest {
    readonly dataset: string

    readonly dataset2?: Dataset
}

/**
 * Request parameters for apiCoreDatasetsDatasetSetDefaultPost operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsDatasetSetDefaultPostRequest {
    readonly dataset: string

    readonly setDefaultDatasetRequest: SetDefaultDatasetRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetUnsetDefaultPost operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsDatasetUnsetDefaultPostRequest {
    readonly dataset: string

    readonly unsetDefaultDatasetRequest: UnsetDefaultDatasetRequest
}

/**
 * Request parameters for apiCoreDatasetsGet operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsGetRequest {
    readonly pageToken?: string

    readonly pageSize?: number

    readonly orderBy?: string

    readonly keyword?: string

    readonly tags?: Array<string>
}

/**
 * Request parameters for apiCoreDatasetsPost operation in DatasetsApi.
 */
export interface DatasetsApiApiCoreDatasetsPostRequest {
    readonly datasetId?: string

    readonly dataset?: Dataset
}

/**
 * DatasetsApi - object-oriented interface
 */
export class DatasetsApi extends BaseAPI {
    
    public apiCoreDatasetsDatasetDelete(requestParameters: DatasetsApiApiCoreDatasetsDatasetDeleteRequest, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsDatasetDelete(requestParameters.dataset, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetGet(requestParameters: DatasetsApiApiCoreDatasetsDatasetGetRequest, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsDatasetGet(requestParameters.dataset, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetPatch(requestParameters: DatasetsApiApiCoreDatasetsDatasetPatchRequest, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsDatasetPatch(requestParameters.dataset, requestParameters.dataset2, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetSetDefaultPost(requestParameters: DatasetsApiApiCoreDatasetsDatasetSetDefaultPostRequest, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsDatasetSetDefaultPost(requestParameters.dataset, requestParameters.setDefaultDatasetRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUnsetDefaultPost(requestParameters: DatasetsApiApiCoreDatasetsDatasetUnsetDefaultPostRequest, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsDatasetUnsetDefaultPost(requestParameters.dataset, requestParameters.unsetDefaultDatasetRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsGet(requestParameters: DatasetsApiApiCoreDatasetsGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsGet(requestParameters.pageToken, requestParameters.pageSize, requestParameters.orderBy, requestParameters.keyword, requestParameters.tags, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsPost(requestParameters: DatasetsApiApiCoreDatasetsPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DatasetsApiFp(this.configuration).apiCoreDatasetsPost(requestParameters.datasetId, requestParameters.dataset, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * DefaultApi - axios parameter creator
 */
export const DefaultApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files and add to knowledge base group
         * @param {string} groupName 
         * @param {boolean} [override] 
         * @param {Array<File>} [files] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreAddFilesToGroupPost: async (groupName: string, override?: boolean, files?: Array<File>, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupName' is not null or undefined
            assertParamExists('apiCoreAddFilesToGroupPost', 'groupName', groupName)
            const localVarPath = `/api/core/add_files_to_group`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;
            const localVarFormParams = new ((configuration && configuration.formDataCtor) || FormData)();

            if (groupName !== undefined) {
                localVarQueryParameter['group_name'] = groupName;
            }

            if (override !== undefined) {
                localVarQueryParameter['override'] = override;
            }

            if (files) {
                files.forEach((element) => {
                    localVarFormParams.append('files', element as any);
                })
            }

            localVarHeaderParameter['Content-Type'] = 'multipart/form-data';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = localVarFormParams;

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary Admin (requires document.write)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreAdminGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/admin`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary Chat with knowledge base
         * @param {ApiCoreChatPostRequest} [apiCoreChatPostRequest] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreChatPost: async (apiCoreChatPostRequest?: ApiCoreChatPostRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/chat`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(apiCoreChatPostRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary Chat with knowledge base (streaming)
         * @param {ApiCoreChatStreamPostRequest} [apiCoreChatStreamPostRequest] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreChatStreamPost: async (apiCoreChatStreamPostRequest?: ApiCoreChatStreamPostRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/chat/stream`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(apiCoreChatStreamPostRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationSwitchStatusGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/conversation:switchStatus`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationSwitchStatusPost: async (conversationSwitchStatusRequest: ConversationSwitchStatusRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationSwitchStatusRequest' is not null or undefined
            assertParamExists('apiCoreConversationSwitchStatusPost', 'conversationSwitchStatusRequest', conversationSwitchStatusRequest)
            const localVarPath = `/api/core/conversation:switchStatus`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(conversationSwitchStatusRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsChatPost: async (body?: object, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/conversations:chat`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(body, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsConversationIdStatusGet: async (conversationId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationId' is not null or undefined
            assertParamExists('apiCoreConversationsConversationIdStatusGet', 'conversationId', conversationId)
            const localVarPath = `/api/core/conversations/{conversation_id}:status`
                .replace(`{${"conversation_id"}}`, encodeURIComponent(String(conversationId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsFeedBackChatHistoryPost: async (conversationFeedbackRequest: ConversationFeedbackRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationFeedbackRequest' is not null or undefined
            assertParamExists('apiCoreConversationsFeedBackChatHistoryPost', 'conversationFeedbackRequest', conversationFeedbackRequest)
            const localVarPath = `/api/core/conversations:feedBackChatHistory`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(conversationFeedbackRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsGet: async (keyword?: string, pageSize?: number, pageToken?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/conversations`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (keyword !== undefined) {
                localVarQueryParameter['keyword'] = keyword;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (pageToken !== undefined) {
                localVarQueryParameter['page_token'] = pageToken;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsNameDelete: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCoreConversationsNameDelete', 'name', name)
            const localVarPath = `/api/core/conversations/{name}`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsNameDetailGet: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCoreConversationsNameDetailGet', 'name', name)
            const localVarPath = `/api/core/conversations/{name}:detail`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsNameGet: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCoreConversationsNameGet', 'name', name)
            const localVarPath = `/api/core/conversations/{name}`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsResumeChatPost: async (conversationResumeRequest: ConversationResumeRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationResumeRequest' is not null or undefined
            assertParamExists('apiCoreConversationsResumeChatPost', 'conversationResumeRequest', conversationResumeRequest)
            const localVarPath = `/api/core/conversations:resumeChat`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'text/event-stream';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(conversationResumeRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsSetChatHistoryPost: async (conversationSetHistoryRequest: ConversationSetHistoryRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationSetHistoryRequest' is not null or undefined
            assertParamExists('apiCoreConversationsSetChatHistoryPost', 'conversationSetHistoryRequest', conversationSetHistoryRequest)
            const localVarPath = `/api/core/conversations:setChatHistory`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(conversationSetHistoryRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreConversationsStopChatGenerationPost: async (conversationStopRequest: ConversationStopRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'conversationStopRequest' is not null or undefined
            assertParamExists('apiCoreConversationsStopChatGenerationPost', 'conversationStopRequest', conversationStopRequest)
            const localVarPath = `/api/core/conversations:stopChatGeneration`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(conversationStopRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetAlgosGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/dataset/algos`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetTagsGet: async (keyword?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/dataset/tags`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (keyword !== undefined) {
                localVarQueryParameter['keyword'] = keyword;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetBatchAddMemberPost: async (dataset: string, batchAddDatasetMemberRequest: BatchAddDatasetMemberRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetBatchAddMemberPost', 'dataset', dataset)
            // verify required parameter 'batchAddDatasetMemberRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetBatchAddMemberPost', 'batchAddDatasetMemberRequest', batchAddDatasetMemberRequest)
            const localVarPath = `/api/core/datasets/{dataset}:batchAddMember`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(batchAddDatasetMemberRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentContentGet: async (dataset: string, document: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentContentGet', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentContentGet', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}:content`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/octet-stream';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentDownloadGet: async (dataset: string, document: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentDownloadGet', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentDownloadGet', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}:download`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/octet-stream';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments
         * @param {string} dataset 
         * @param {string} document 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet: async (dataset: string, document: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}/segments`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments/{segment}
         * @param {string} dataset 
         * @param {string} document 
         * @param {string} segment 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet: async (dataset: string, document: string, segment: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet', 'document', document)
            // verify required parameter 'segment' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet', 'segment', segment)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}/segments/{segment}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)))
                .replace(`{${"segment"}}`, encodeURIComponent(String(segment)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetMembersGet: async (dataset: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersGet', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/members`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetMembersSearchPost: async (dataset: string, searchDatasetMemberRequest?: SearchDatasetMemberRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersSearchPost', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/members:search`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(searchDatasetMemberRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetMembersUserIdDelete: async (dataset: string, userId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdDelete', 'dataset', dataset)
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdDelete', 'userId', userId)
            const localVarPath = `/api/core/datasets/{dataset}/members/{user_id}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"user_id"}}`, encodeURIComponent(String(userId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetMembersUserIdGet: async (dataset: string, userId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdGet', 'dataset', dataset)
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdGet', 'userId', userId)
            const localVarPath = `/api/core/datasets/{dataset}/members/{user_id}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"user_id"}}`, encodeURIComponent(String(userId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetMembersUserIdPatch: async (dataset: string, userId: string, updateDatasetMemberRequest: UpdateDatasetMemberRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdPatch', 'dataset', dataset)
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdPatch', 'userId', userId)
            // verify required parameter 'updateDatasetMemberRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetMembersUserIdPatch', 'updateDatasetMemberRequest', updateDatasetMemberRequest)
            const localVarPath = `/api/core/datasets/{dataset}/members/{user_id}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"user_id"}}`, encodeURIComponent(String(userId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(updateDatasetMemberRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksBatchUploadPost: async (dataset: string, documentPid?: string, documentTags?: string, files?: Array<File>, relativePath?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksBatchUploadPost', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/tasks:batchUpload`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;
            const localVarFormParams = new ((configuration && configuration.formDataCtor) || FormData)();


            if (documentPid !== undefined) { 
                localVarFormParams.append('document_pid', documentPid as any);
            }

            if (documentTags !== undefined) { 
                localVarFormParams.append('document_tags', documentTags as any);
            }
            if (files) {
                files.forEach((element) => {
                    localVarFormParams.append('files', element as any);
                })
            }


            if (relativePath !== undefined) { 
                localVarFormParams.append('relative_path', relativePath as any);
            }
            localVarHeaderParameter['Content-Type'] = 'multipart/form-data';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = localVarFormParams;

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsPost: async (dataset: string, documentPid?: string, documentTags?: string, files?: Array<File>, relativePath?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsPost', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/uploads`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;
            const localVarFormParams = new ((configuration && configuration.formDataCtor) || FormData)();


            if (documentPid !== undefined) { 
                localVarFormParams.append('document_pid', documentPid as any);
            }

            if (documentTags !== undefined) { 
                localVarFormParams.append('document_tags', documentTags as any);
            }
            if (files) {
                files.forEach((element) => {
                    localVarFormParams.append('files', element as any);
                })
            }


            if (relativePath !== undefined) { 
                localVarFormParams.append('relative_path', relativePath as any);
            }
            localVarHeaderParameter['Content-Type'] = 'multipart/form-data';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = localVarFormParams;

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsUploadFileIdContentGet: async (dataset: string, uploadFileId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadFileIdContentGet', 'dataset', dataset)
            // verify required parameter 'uploadFileId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadFileIdContentGet', 'uploadFileId', uploadFileId)
            const localVarPath = `/api/core/datasets/{dataset}/uploads/{upload_file_id}:content`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"upload_file_id"}}`, encodeURIComponent(String(uploadFileId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/octet-stream';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet: async (dataset: string, uploadFileId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet', 'dataset', dataset)
            // verify required parameter 'uploadFileId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet', 'uploadFileId', uploadFileId)
            const localVarPath = `/api/core/datasets/{dataset}/uploads/{upload_file_id}:download`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"upload_file_id"}}`, encodeURIComponent(String(uploadFileId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/octet-stream';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDocumentCreatorsGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/document/creators`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDocumentTagsGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/document/tags`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary Health check
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreHealthGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/health`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary Hello (requires user.read)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreHelloGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/hello`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbGrantPrincipalsGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/kb/grant-principals`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAclAclIdDelete: async (kbId: string, aclId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclAclIdDelete', 'kbId', kbId)
            // verify required parameter 'aclId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclAclIdDelete', 'aclId', aclId)
            const localVarPath = `/api/core/kb/{kb_id}/acl/{acl_id}`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)))
                .replace(`{${"acl_id"}}`, encodeURIComponent(String(aclId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAclAclIdPut: async (kbId: string, aclId: string, updateACLRequest: UpdateACLRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclAclIdPut', 'kbId', kbId)
            // verify required parameter 'aclId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclAclIdPut', 'aclId', aclId)
            // verify required parameter 'updateACLRequest' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclAclIdPut', 'updateACLRequest', updateACLRequest)
            const localVarPath = `/api/core/kb/{kb_id}/acl/{acl_id}`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)))
                .replace(`{${"acl_id"}}`, encodeURIComponent(String(aclId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PUT', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(updateACLRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAclBatchPost: async (kbId: string, batchAddACLRequest: BatchAddACLRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclBatchPost', 'kbId', kbId)
            // verify required parameter 'batchAddACLRequest' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclBatchPost', 'batchAddACLRequest', batchAddACLRequest)
            const localVarPath = `/api/core/kb/{kb_id}/acl/batch`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(batchAddACLRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAclGet: async (kbId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclGet', 'kbId', kbId)
            const localVarPath = `/api/core/kb/{kb_id}/acl`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAclPost: async (kbId: string, addACLRequest: AddACLRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclPost', 'kbId', kbId)
            // verify required parameter 'addACLRequest' is not null or undefined
            assertParamExists('apiCoreKbKbIdAclPost', 'addACLRequest', addACLRequest)
            const localVarPath = `/api/core/kb/{kb_id}/acl`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(addACLRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAuthorizationGet: async (kbId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAuthorizationGet', 'kbId', kbId)
            const localVarPath = `/api/core/kb/{kb_id}/authorization`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdAuthorizationPost: async (kbId: string, setKBAuthorizationRequest: SetKBAuthorizationRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdAuthorizationPost', 'kbId', kbId)
            // verify required parameter 'setKBAuthorizationRequest' is not null or undefined
            assertParamExists('apiCoreKbKbIdAuthorizationPost', 'setKBAuthorizationRequest', setKBAuthorizationRequest)
            const localVarPath = `/api/core/kb/{kb_id}/authorization`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(setKBAuthorizationRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdCanGet: async (kbId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdCanGet', 'kbId', kbId)
            const localVarPath = `/api/core/kb/{kb_id}/can`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbKbIdPermissionGet: async (kbId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'kbId' is not null or undefined
            assertParamExists('apiCoreKbKbIdPermissionGet', 'kbId', kbId)
            const localVarPath = `/api/core/kb/{kb_id}/permission`
                .replace(`{${"kb_id"}}`, encodeURIComponent(String(kbId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbListGet: async (permission?: string, keyword?: string, page?: number, pageSize?: number, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/kb/list`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (permission !== undefined) {
                localVarQueryParameter['permission'] = permission;
            }

            if (keyword !== undefined) {
                localVarQueryParameter['keyword'] = keyword;
            }

            if (page !== undefined) {
                localVarQueryParameter['page'] = page;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreKbPermissionBatchPost: async (permissionBatchRequest: PermissionBatchRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'permissionBatchRequest' is not null or undefined
            assertParamExists('apiCoreKbPermissionBatchPost', 'permissionBatchRequest', permissionBatchRequest)
            const localVarPath = `/api/core/kb/permission/batch`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(permissionBatchRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * Proxies to parsing service.
         * @summary List files in knowledge base
         * @param {number} [limit] 
         * @param {boolean} [details] 
         * @param {boolean} [alive] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListFilesGet: async (limit?: number, details?: boolean, alive?: boolean, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/list_files`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (limit !== undefined) {
                localVarQueryParameter['limit'] = limit;
            }

            if (details !== undefined) {
                localVarQueryParameter['details'] = details;
            }

            if (alive !== undefined) {
                localVarQueryParameter['alive'] = alive;
            }


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary List files in a knowledge base group
         * @param {string} [groupName] 
         * @param {number} [limit] 
         * @param {boolean} [alive] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListFilesInGroupGet: async (groupName?: string, limit?: number, alive?: boolean, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/list_files_in_group`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (groupName !== undefined) {
                localVarQueryParameter['group_name'] = groupName;
            }

            if (limit !== undefined) {
                localVarQueryParameter['limit'] = limit;
            }

            if (alive !== undefined) {
                localVarQueryParameter['alive'] = alive;
            }


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary List knowledge base groups
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListKbGroupsGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/list_kb_groups`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsGet: async (pageSize?: number, pageToken?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/prompts`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (pageToken !== undefined) {
                localVarQueryParameter['page_token'] = pageToken;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsNameDelete: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCorePromptsNameDelete', 'name', name)
            const localVarPath = `/api/core/prompts/{name}`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsNameGet: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCorePromptsNameGet', 'name', name)
            const localVarPath = `/api/core/prompts/{name}`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsNamePatch: async (name: string, promptPatchRequest: PromptPatchRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCorePromptsNamePatch', 'name', name)
            // verify required parameter 'promptPatchRequest' is not null or undefined
            assertParamExists('apiCorePromptsNamePatch', 'promptPatchRequest', promptPatchRequest)
            const localVarPath = `/api/core/prompts/{name}`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(promptPatchRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsNameSetDefaultPost: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCorePromptsNameSetDefaultPost', 'name', name)
            const localVarPath = `/api/core/prompts/{name}:setDefault`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsNameUnsetDefaultPost: async (name: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'name' is not null or undefined
            assertParamExists('apiCorePromptsNameUnsetDefaultPost', 'name', name)
            const localVarPath = `/api/core/prompts/{name}:unsetDefault`
                .replace(`{${"name"}}`, encodeURIComponent(String(name)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCorePromptsPost: async (promptRequest: PromptRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'promptRequest' is not null or undefined
            assertParamExists('apiCorePromptsPost', 'promptRequest', promptRequest)
            const localVarPath = `/api/core/prompts`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(promptRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * 
         * @summary GET /static-files/{path:.*}
         * @param {string} path 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreStaticFilesPathGet: async (path: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'path' is not null or undefined
            assertParamExists('apiCoreStaticFilesPathGet', 'path', path)
            const localVarPath = `/api/core/static-files/{path:.*}`
                .replace(`{${"path:.*"}}`, encodeURIComponent(String(path)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;


            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreTempUploadsPost: async (files?: Array<File>, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/temp/uploads`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;
            const localVarFormParams = new ((configuration && configuration.formDataCtor) || FormData)();

            if (files) {
                files.forEach((element) => {
                    localVarFormParams.append('files', element as any);
                })
            }

            localVarHeaderParameter['Content-Type'] = 'multipart/form-data';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = localVarFormParams;

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files to knowledge base
         * @param {boolean} [override] 
         * @param {string} [metadatas] 
         * @param {string} [userPath] 
         * @param {Array<File>} [files] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreUploadFilesPost: async (override?: boolean, metadatas?: string, userPath?: string, files?: Array<File>, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/upload_files`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;
            const localVarFormParams = new ((configuration && configuration.formDataCtor) || FormData)();

            if (override !== undefined) {
                localVarQueryParameter['override'] = override;
            }

            if (metadatas !== undefined) {
                localVarQueryParameter['metadatas'] = metadatas;
            }

            if (userPath !== undefined) {
                localVarQueryParameter['user_path'] = userPath;
            }

            if (files) {
                files.forEach((element) => {
                    localVarFormParams.append('files', element as any);
                })
            }

            localVarHeaderParameter['Content-Type'] = 'multipart/form-data';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = localVarFormParams;

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * DefaultApi - functional programming interface
 */
export const DefaultApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = DefaultApiAxiosParamCreator(configuration)
    return {
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files and add to knowledge base group
         * @param {string} groupName 
         * @param {boolean} [override] 
         * @param {Array<File>} [files] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreAddFilesToGroupPost(groupName: string, override?: boolean, files?: Array<File>, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreAddFilesToGroupPost(groupName, override, files, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreAddFilesToGroupPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary Admin (requires document.write)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreAdminGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreAdminGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreAdminGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary Chat with knowledge base
         * @param {ApiCoreChatPostRequest} [apiCoreChatPostRequest] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreChatPost(apiCoreChatPostRequest?: ApiCoreChatPostRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreChatPost(apiCoreChatPostRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreChatPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary Chat with knowledge base (streaming)
         * @param {ApiCoreChatStreamPostRequest} [apiCoreChatStreamPostRequest] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreChatStreamPost(apiCoreChatStreamPostRequest?: ApiCoreChatStreamPostRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreChatStreamPost(apiCoreChatStreamPostRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreChatStreamPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationSwitchStatusGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationSwitchStatusResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationSwitchStatusGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationSwitchStatusGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationSwitchStatusPost(conversationSwitchStatusRequest: ConversationSwitchStatusRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationSwitchStatusResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationSwitchStatusPost(conversationSwitchStatusRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationSwitchStatusPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsChatPost(body?: object, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsChatPost(body, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsChatPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsConversationIdStatusGet(conversationId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationChatStatusResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsConversationIdStatusGet(conversationId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsConversationIdStatusGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsFeedBackChatHistoryPost(conversationFeedbackRequest: ConversationFeedbackRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsFeedBackChatHistoryPost(conversationFeedbackRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsFeedBackChatHistoryPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsGet(keyword?: string, pageSize?: number, pageToken?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationListResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsGet(keyword, pageSize, pageToken, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsNameDelete(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsNameDelete(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsNameDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsNameDetailGet(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationDetailResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsNameDetailGet(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsNameDetailGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsNameGet(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ConversationItem>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsNameGet(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsNameGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsResumeChatPost(conversationResumeRequest: ConversationResumeRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ChatChunkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsResumeChatPost(conversationResumeRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsResumeChatPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsSetChatHistoryPost(conversationSetHistoryRequest: ConversationSetHistoryRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<SetChatHistoryResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsSetChatHistoryPost(conversationSetHistoryRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsSetChatHistoryPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreConversationsStopChatGenerationPost(conversationStopRequest: ConversationStopRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreConversationsStopChatGenerationPost(conversationStopRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreConversationsStopChatGenerationPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetAlgosGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListAlgosResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetAlgosGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetAlgosGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetTagsGet(keyword?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<AllDatasetTagsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetTagsGet(keyword, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetTagsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetBatchAddMemberPost(dataset: string, batchAddDatasetMemberRequest: BatchAddDatasetMemberRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<BatchAddDatasetMemberResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetBatchAddMemberPost(dataset, batchAddDatasetMemberRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetBatchAddMemberPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsDocumentContentGet(dataset: string, document: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<File>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentContentGet(dataset, document, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetDocumentsDocumentContentGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(dataset: string, document: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<File>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(dataset, document, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetDocumentsDocumentDownloadGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments
         * @param {string} dataset 
         * @param {string} document 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(dataset: string, document: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(dataset, document, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments/{segment}
         * @param {string} dataset 
         * @param {string} document 
         * @param {string} segment 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(dataset: string, document: string, segment: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(dataset, document, segment, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetMembersGet(dataset: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDatasetMembersResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetMembersGet(dataset, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetMembersGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetMembersSearchPost(dataset: string, searchDatasetMemberRequest?: SearchDatasetMemberRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDatasetMembersResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetMembersSearchPost(dataset, searchDatasetMemberRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetMembersSearchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetMembersUserIdDelete(dataset: string, userId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetMembersUserIdDelete(dataset, userId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetMembersUserIdDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetMembersUserIdGet(dataset: string, userId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<DatasetMember>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetMembersUserIdGet(dataset, userId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetMembersUserIdGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetMembersUserIdPatch(dataset: string, userId: string, updateDatasetMemberRequest: UpdateDatasetMemberRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<DatasetMember>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetMembersUserIdPatch(dataset, userId, updateDatasetMemberRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetMembersUserIdPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksBatchUploadPost(dataset: string, documentPid?: string, documentTags?: string, files?: Array<File>, relativePath?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<BatchUploadTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksBatchUploadPost(dataset, documentPid, documentTags, files, relativePath, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetTasksBatchUploadPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsPost(dataset: string, documentPid?: string, documentTags?: string, files?: Array<File>, relativePath?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UploadFilesResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsPost(dataset, documentPid, documentTags, files, relativePath, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetUploadsPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(dataset: string, uploadFileId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<File>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(dataset, uploadFileId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetUploadsUploadFileIdContentGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(dataset: string, uploadFileId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<File>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(dataset, uploadFileId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDocumentCreatorsGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<DocumentCreatorsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDocumentCreatorsGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDocumentCreatorsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDocumentTagsGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<DocumentTagsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDocumentTagsGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreDocumentTagsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary Health check
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreHealthGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreHealthGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreHealthGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary Hello (requires user.read)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreHelloGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreHelloGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreHelloGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbGrantPrincipalsGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbGrantPrincipalsGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbGrantPrincipalsGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbGrantPrincipalsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAclAclIdDelete(kbId: string, aclId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAclAclIdPut200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAclAclIdDelete(kbId, aclId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAclAclIdDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAclAclIdPut(kbId: string, aclId: string, updateACLRequest: UpdateACLRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAclAclIdPut200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAclAclIdPut(kbId, aclId, updateACLRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAclAclIdPut']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAclBatchPost(kbId: string, batchAddACLRequest: BatchAddACLRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAclBatchPost200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAclBatchPost(kbId, batchAddACLRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAclBatchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAclGet(kbId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAclGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAclGet(kbId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAclGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAclPost(kbId: string, addACLRequest: AddACLRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAclPost200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAclPost(kbId, addACLRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAclPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAuthorizationGet(kbId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAuthorizationGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAuthorizationGet(kbId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAuthorizationGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdAuthorizationPost(kbId: string, setKBAuthorizationRequest: SetKBAuthorizationRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdAuthorizationPost200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdAuthorizationPost(kbId, setKBAuthorizationRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdAuthorizationPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdCanGet(kbId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdCanGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdCanGet(kbId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdCanGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbKbIdPermissionGet(kbId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbKbIdPermissionGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbKbIdPermissionGet(kbId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbKbIdPermissionGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbListGet(permission?: string, keyword?: string, page?: number, pageSize?: number, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbListGet200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbListGet(permission, keyword, page, pageSize, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbListGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreKbPermissionBatchPost(permissionBatchRequest: PermissionBatchRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ApiCoreKbPermissionBatchPost200Response>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreKbPermissionBatchPost(permissionBatchRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreKbPermissionBatchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * Proxies to parsing service.
         * @summary List files in knowledge base
         * @param {number} [limit] 
         * @param {boolean} [details] 
         * @param {boolean} [alive] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreListFilesGet(limit?: number, details?: boolean, alive?: boolean, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreListFilesGet(limit, details, alive, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreListFilesGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary List files in a knowledge base group
         * @param {string} [groupName] 
         * @param {number} [limit] 
         * @param {boolean} [alive] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreListFilesInGroupGet(groupName?: string, limit?: number, alive?: boolean, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreListFilesInGroupGet(groupName, limit, alive, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreListFilesInGroupGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary List knowledge base groups
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreListKbGroupsGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreListKbGroupsGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreListKbGroupsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsGet(pageSize?: number, pageToken?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<PromptListResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsGet(pageSize, pageToken, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsNameDelete(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsNameDelete(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsNameDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsNameGet(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<PromptItem>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsNameGet(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsNameGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsNamePatch(name: string, promptPatchRequest: PromptPatchRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<PromptItem>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsNamePatch(name, promptPatchRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsNamePatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsNameSetDefaultPost(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsNameSetDefaultPost(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsNameSetDefaultPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsNameUnsetDefaultPost(name: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsNameUnsetDefaultPost(name, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsNameUnsetDefaultPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCorePromptsPost(promptRequest: PromptRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<PromptItem>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCorePromptsPost(promptRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCorePromptsPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * 
         * @summary GET /static-files/{path:.*}
         * @param {string} path 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreStaticFilesPathGet(path: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreStaticFilesPathGet(path, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreStaticFilesPathGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreTempUploadsPost(files?: Array<File>, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UploadFilesResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreTempUploadsPost(files, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreTempUploadsPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files to knowledge base
         * @param {boolean} [override] 
         * @param {string} [metadatas] 
         * @param {string} [userPath] 
         * @param {Array<File>} [files] 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async apiCoreUploadFilesPost(override?: boolean, metadatas?: string, userPath?: string, files?: Array<File>, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<void>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreUploadFilesPost(override, metadatas, userPath, files, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DefaultApi.apiCoreUploadFilesPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * DefaultApi - factory interface
 */
export const DefaultApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = DefaultApiFp(configuration)
    return {
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files and add to knowledge base group
         * @param {DefaultApiApiCoreAddFilesToGroupPostRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreAddFilesToGroupPost(requestParameters: DefaultApiApiCoreAddFilesToGroupPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreAddFilesToGroupPost(requestParameters.groupName, requestParameters.override, requestParameters.files, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary Admin (requires document.write)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreAdminGet(options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreAdminGet(options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary Chat with knowledge base
         * @param {DefaultApiApiCoreChatPostRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreChatPost(requestParameters: DefaultApiApiCoreChatPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreChatPost(requestParameters.apiCoreChatPostRequest, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary Chat with knowledge base (streaming)
         * @param {DefaultApiApiCoreChatStreamPostRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreChatStreamPost(requestParameters: DefaultApiApiCoreChatStreamPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreChatStreamPost(requestParameters.apiCoreChatStreamPostRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationSwitchStatusGet(options?: RawAxiosRequestConfig): AxiosPromise<ConversationSwitchStatusResponse> {
            return localVarFp.apiCoreConversationSwitchStatusGet(options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationSwitchStatusPost(requestParameters: DefaultApiApiCoreConversationSwitchStatusPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ConversationSwitchStatusResponse> {
            return localVarFp.apiCoreConversationSwitchStatusPost(requestParameters.conversationSwitchStatusRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsChatPost(requestParameters: DefaultApiApiCoreConversationsChatPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreConversationsChatPost(requestParameters.body, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsConversationIdStatusGet(requestParameters: DefaultApiApiCoreConversationsConversationIdStatusGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ConversationChatStatusResponse> {
            return localVarFp.apiCoreConversationsConversationIdStatusGet(requestParameters.conversationId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsFeedBackChatHistoryPost(requestParameters: DefaultApiApiCoreConversationsFeedBackChatHistoryPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreConversationsFeedBackChatHistoryPost(requestParameters.conversationFeedbackRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsGet(requestParameters: DefaultApiApiCoreConversationsGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<ConversationListResponse> {
            return localVarFp.apiCoreConversationsGet(requestParameters.keyword, requestParameters.pageSize, requestParameters.pageToken, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsNameDelete(requestParameters: DefaultApiApiCoreConversationsNameDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreConversationsNameDelete(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsNameDetailGet(requestParameters: DefaultApiApiCoreConversationsNameDetailGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ConversationDetailResponse> {
            return localVarFp.apiCoreConversationsNameDetailGet(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsNameGet(requestParameters: DefaultApiApiCoreConversationsNameGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ConversationItem> {
            return localVarFp.apiCoreConversationsNameGet(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsResumeChatPost(requestParameters: DefaultApiApiCoreConversationsResumeChatPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ChatChunkResponse> {
            return localVarFp.apiCoreConversationsResumeChatPost(requestParameters.conversationResumeRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsSetChatHistoryPost(requestParameters: DefaultApiApiCoreConversationsSetChatHistoryPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<SetChatHistoryResponse> {
            return localVarFp.apiCoreConversationsSetChatHistoryPost(requestParameters.conversationSetHistoryRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreConversationsStopChatGenerationPost(requestParameters: DefaultApiApiCoreConversationsStopChatGenerationPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreConversationsStopChatGenerationPost(requestParameters.conversationStopRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetAlgosGet(options?: RawAxiosRequestConfig): AxiosPromise<ListAlgosResponse> {
            return localVarFp.apiCoreDatasetAlgosGet(options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetTagsGet(requestParameters: DefaultApiApiCoreDatasetTagsGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<AllDatasetTagsResponse> {
            return localVarFp.apiCoreDatasetTagsGet(requestParameters.keyword, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetBatchAddMemberPost(requestParameters: DefaultApiApiCoreDatasetsDatasetBatchAddMemberPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<BatchAddDatasetMemberResponse> {
            return localVarFp.apiCoreDatasetsDatasetBatchAddMemberPost(requestParameters.dataset, requestParameters.batchAddDatasetMemberRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentContentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentContentGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<File> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentContentGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentDownloadGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<File> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments
         * @param {DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsGetRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary GET /datasets/{dataset}/documents/{document}/segments/{segment}
         * @param {DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGetRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(requestParameters.dataset, requestParameters.document, requestParameters.segment, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetMembersGet(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListDatasetMembersResponse> {
            return localVarFp.apiCoreDatasetsDatasetMembersGet(requestParameters.dataset, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetMembersSearchPost(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersSearchPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListDatasetMembersResponse> {
            return localVarFp.apiCoreDatasetsDatasetMembersSearchPost(requestParameters.dataset, requestParameters.searchDatasetMemberRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetMembersUserIdDelete(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetMembersUserIdDelete(requestParameters.dataset, requestParameters.userId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetMembersUserIdGet(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<DatasetMember> {
            return localVarFp.apiCoreDatasetsDatasetMembersUserIdGet(requestParameters.dataset, requestParameters.userId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetMembersUserIdPatch(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<DatasetMember> {
            return localVarFp.apiCoreDatasetsDatasetMembersUserIdPatch(requestParameters.dataset, requestParameters.userId, requestParameters.updateDatasetMemberRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksBatchUploadPost(requestParameters: DefaultApiApiCoreDatasetsDatasetTasksBatchUploadPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<BatchUploadTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksBatchUploadPost(requestParameters.dataset, requestParameters.documentPid, requestParameters.documentTags, requestParameters.files, requestParameters.relativePath, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsPost(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<UploadFilesResponse> {
            return localVarFp.apiCoreDatasetsDatasetUploadsPost(requestParameters.dataset, requestParameters.documentPid, requestParameters.documentTags, requestParameters.files, requestParameters.relativePath, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdContentGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<File> {
            return localVarFp.apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(requestParameters.dataset, requestParameters.uploadFileId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdDownloadGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<File> {
            return localVarFp.apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(requestParameters.dataset, requestParameters.uploadFileId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDocumentCreatorsGet(options?: RawAxiosRequestConfig): AxiosPromise<DocumentCreatorsResponse> {
            return localVarFp.apiCoreDocumentCreatorsGet(options).then((request) => request(axios, basePath));
        },
        
        apiCoreDocumentTagsGet(options?: RawAxiosRequestConfig): AxiosPromise<DocumentTagsResponse> {
            return localVarFp.apiCoreDocumentTagsGet(options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary Health check
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreHealthGet(options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreHealthGet(options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary Hello (requires user.read)
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreHelloGet(options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreHelloGet(options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbGrantPrincipalsGet(options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbGrantPrincipalsGet200Response> {
            return localVarFp.apiCoreKbGrantPrincipalsGet(options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAclAclIdDelete(requestParameters: DefaultApiApiCoreKbKbIdAclAclIdDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAclAclIdPut200Response> {
            return localVarFp.apiCoreKbKbIdAclAclIdDelete(requestParameters.kbId, requestParameters.aclId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAclAclIdPut(requestParameters: DefaultApiApiCoreKbKbIdAclAclIdPutRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAclAclIdPut200Response> {
            return localVarFp.apiCoreKbKbIdAclAclIdPut(requestParameters.kbId, requestParameters.aclId, requestParameters.updateACLRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAclBatchPost(requestParameters: DefaultApiApiCoreKbKbIdAclBatchPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAclBatchPost200Response> {
            return localVarFp.apiCoreKbKbIdAclBatchPost(requestParameters.kbId, requestParameters.batchAddACLRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAclGet(requestParameters: DefaultApiApiCoreKbKbIdAclGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAclGet200Response> {
            return localVarFp.apiCoreKbKbIdAclGet(requestParameters.kbId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAclPost(requestParameters: DefaultApiApiCoreKbKbIdAclPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAclPost200Response> {
            return localVarFp.apiCoreKbKbIdAclPost(requestParameters.kbId, requestParameters.addACLRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAuthorizationGet(requestParameters: DefaultApiApiCoreKbKbIdAuthorizationGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAuthorizationGet200Response> {
            return localVarFp.apiCoreKbKbIdAuthorizationGet(requestParameters.kbId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdAuthorizationPost(requestParameters: DefaultApiApiCoreKbKbIdAuthorizationPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdAuthorizationPost200Response> {
            return localVarFp.apiCoreKbKbIdAuthorizationPost(requestParameters.kbId, requestParameters.setKBAuthorizationRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdCanGet(requestParameters: DefaultApiApiCoreKbKbIdCanGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdCanGet200Response> {
            return localVarFp.apiCoreKbKbIdCanGet(requestParameters.kbId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbKbIdPermissionGet(requestParameters: DefaultApiApiCoreKbKbIdPermissionGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbKbIdPermissionGet200Response> {
            return localVarFp.apiCoreKbKbIdPermissionGet(requestParameters.kbId, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbListGet(requestParameters: DefaultApiApiCoreKbListGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbListGet200Response> {
            return localVarFp.apiCoreKbListGet(requestParameters.permission, requestParameters.keyword, requestParameters.page, requestParameters.pageSize, options).then((request) => request(axios, basePath));
        },
        
        apiCoreKbPermissionBatchPost(requestParameters: DefaultApiApiCoreKbPermissionBatchPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ApiCoreKbPermissionBatchPost200Response> {
            return localVarFp.apiCoreKbPermissionBatchPost(requestParameters.permissionBatchRequest, options).then((request) => request(axios, basePath));
        },
        /**
         * Proxies to parsing service.
         * @summary List files in knowledge base
         * @param {DefaultApiApiCoreListFilesGetRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListFilesGet(requestParameters: DefaultApiApiCoreListFilesGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreListFilesGet(requestParameters.limit, requestParameters.details, requestParameters.alive, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary List files in a knowledge base group
         * @param {DefaultApiApiCoreListFilesInGroupGetRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListFilesInGroupGet(requestParameters: DefaultApiApiCoreListFilesInGroupGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreListFilesInGroupGet(requestParameters.groupName, requestParameters.limit, requestParameters.alive, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary List knowledge base groups
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreListKbGroupsGet(options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreListKbGroupsGet(options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsGet(requestParameters: DefaultApiApiCorePromptsGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<PromptListResponse> {
            return localVarFp.apiCorePromptsGet(requestParameters.pageSize, requestParameters.pageToken, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsNameDelete(requestParameters: DefaultApiApiCorePromptsNameDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCorePromptsNameDelete(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsNameGet(requestParameters: DefaultApiApiCorePromptsNameGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<PromptItem> {
            return localVarFp.apiCorePromptsNameGet(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsNamePatch(requestParameters: DefaultApiApiCorePromptsNamePatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<PromptItem> {
            return localVarFp.apiCorePromptsNamePatch(requestParameters.name, requestParameters.promptPatchRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsNameSetDefaultPost(requestParameters: DefaultApiApiCorePromptsNameSetDefaultPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCorePromptsNameSetDefaultPost(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsNameUnsetDefaultPost(requestParameters: DefaultApiApiCorePromptsNameUnsetDefaultPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCorePromptsNameUnsetDefaultPost(requestParameters.name, options).then((request) => request(axios, basePath));
        },
        
        apiCorePromptsPost(requestParameters: DefaultApiApiCorePromptsPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<PromptItem> {
            return localVarFp.apiCorePromptsPost(requestParameters.promptRequest, options).then((request) => request(axios, basePath));
        },
        /**
         * 
         * @summary GET /static-files/{path:.*}
         * @param {DefaultApiApiCoreStaticFilesPathGetRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreStaticFilesPathGet(requestParameters: DefaultApiApiCoreStaticFilesPathGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreStaticFilesPathGet(requestParameters.path, options).then((request) => request(axios, basePath));
        },
        
        apiCoreTempUploadsPost(requestParameters: DefaultApiApiCoreTempUploadsPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<UploadFilesResponse> {
            return localVarFp.apiCoreTempUploadsPost(requestParameters.files, options).then((request) => request(axios, basePath));
        },
        /**
         * Proxies to parsing service. Multipart form with files.
         * @summary Upload files to knowledge base
         * @param {DefaultApiApiCoreUploadFilesPostRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        apiCoreUploadFilesPost(requestParameters: DefaultApiApiCoreUploadFilesPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<void> {
            return localVarFp.apiCoreUploadFilesPost(requestParameters.override, requestParameters.metadatas, requestParameters.userPath, requestParameters.files, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for apiCoreAddFilesToGroupPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreAddFilesToGroupPostRequest {
    readonly groupName: string

    readonly override?: boolean

    readonly files?: Array<File>
}

/**
 * Request parameters for apiCoreChatPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreChatPostRequest {
    readonly apiCoreChatPostRequest?: ApiCoreChatPostRequest
}

/**
 * Request parameters for apiCoreChatStreamPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreChatStreamPostRequest {
    readonly apiCoreChatStreamPostRequest?: ApiCoreChatStreamPostRequest
}

/**
 * Request parameters for apiCoreConversationSwitchStatusPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationSwitchStatusPostRequest {
    readonly conversationSwitchStatusRequest: ConversationSwitchStatusRequest
}

/**
 * Request parameters for apiCoreConversationsChatPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsChatPostRequest {
    readonly body?: object
}

/**
 * Request parameters for apiCoreConversationsConversationIdStatusGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsConversationIdStatusGetRequest {
    readonly conversationId: string
}

/**
 * Request parameters for apiCoreConversationsFeedBackChatHistoryPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsFeedBackChatHistoryPostRequest {
    readonly conversationFeedbackRequest: ConversationFeedbackRequest
}

/**
 * Request parameters for apiCoreConversationsGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsGetRequest {
    readonly keyword?: string

    readonly pageSize?: number

    readonly pageToken?: string
}

/**
 * Request parameters for apiCoreConversationsNameDelete operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsNameDeleteRequest {
    readonly name: string
}

/**
 * Request parameters for apiCoreConversationsNameDetailGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsNameDetailGetRequest {
    readonly name: string
}

/**
 * Request parameters for apiCoreConversationsNameGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsNameGetRequest {
    readonly name: string
}

/**
 * Request parameters for apiCoreConversationsResumeChatPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsResumeChatPostRequest {
    readonly conversationResumeRequest: ConversationResumeRequest
}

/**
 * Request parameters for apiCoreConversationsSetChatHistoryPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsSetChatHistoryPostRequest {
    readonly conversationSetHistoryRequest: ConversationSetHistoryRequest
}

/**
 * Request parameters for apiCoreConversationsStopChatGenerationPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreConversationsStopChatGenerationPostRequest {
    readonly conversationStopRequest: ConversationStopRequest
}

/**
 * Request parameters for apiCoreDatasetTagsGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetTagsGetRequest {
    readonly keyword?: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetBatchAddMemberPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetBatchAddMemberPostRequest {
    readonly dataset: string

    readonly batchAddDatasetMemberRequest: BatchAddDatasetMemberRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentContentGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetDocumentsDocumentContentGetRequest {
    readonly dataset: string

    readonly document: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentDownloadGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetDocumentsDocumentDownloadGetRequest {
    readonly dataset: string

    readonly document: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsGetRequest {
    readonly dataset: string

    readonly document: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGetRequest {
    readonly dataset: string

    readonly document: string

    readonly segment: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetMembersGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetMembersGetRequest {
    readonly dataset: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetMembersSearchPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetMembersSearchPostRequest {
    readonly dataset: string

    readonly searchDatasetMemberRequest?: SearchDatasetMemberRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetMembersUserIdDelete operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetMembersUserIdDeleteRequest {
    readonly dataset: string

    readonly userId: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetMembersUserIdGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetMembersUserIdGetRequest {
    readonly dataset: string

    readonly userId: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetMembersUserIdPatch operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetMembersUserIdPatchRequest {
    readonly dataset: string

    readonly userId: string

    readonly updateDatasetMemberRequest: UpdateDatasetMemberRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksBatchUploadPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetTasksBatchUploadPostRequest {
    readonly dataset: string

    readonly documentPid?: string

    readonly documentTags?: string

    readonly files?: Array<File>

    readonly relativePath?: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetUploadsPostRequest {
    readonly dataset: string

    readonly documentPid?: string

    readonly documentTags?: string

    readonly files?: Array<File>

    readonly relativePath?: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsUploadFileIdContentGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdContentGetRequest {
    readonly dataset: string

    readonly uploadFileId: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdDownloadGetRequest {
    readonly dataset: string

    readonly uploadFileId: string
}

/**
 * Request parameters for apiCoreKbKbIdAclAclIdDelete operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAclAclIdDeleteRequest {
    readonly kbId: string

    readonly aclId: string
}

/**
 * Request parameters for apiCoreKbKbIdAclAclIdPut operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAclAclIdPutRequest {
    readonly kbId: string

    readonly aclId: string

    readonly updateACLRequest: UpdateACLRequest
}

/**
 * Request parameters for apiCoreKbKbIdAclBatchPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAclBatchPostRequest {
    readonly kbId: string

    readonly batchAddACLRequest: BatchAddACLRequest
}

/**
 * Request parameters for apiCoreKbKbIdAclGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAclGetRequest {
    readonly kbId: string
}

/**
 * Request parameters for apiCoreKbKbIdAclPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAclPostRequest {
    readonly kbId: string

    readonly addACLRequest: AddACLRequest
}

/**
 * Request parameters for apiCoreKbKbIdAuthorizationGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAuthorizationGetRequest {
    readonly kbId: string
}

/**
 * Request parameters for apiCoreKbKbIdAuthorizationPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdAuthorizationPostRequest {
    readonly kbId: string

    readonly setKBAuthorizationRequest: SetKBAuthorizationRequest
}

/**
 * Request parameters for apiCoreKbKbIdCanGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdCanGetRequest {
    readonly kbId: string
}

/**
 * Request parameters for apiCoreKbKbIdPermissionGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbKbIdPermissionGetRequest {
    readonly kbId: string
}

/**
 * Request parameters for apiCoreKbListGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbListGetRequest {
    readonly permission?: string

    readonly keyword?: string

    readonly page?: number

    readonly pageSize?: number
}

/**
 * Request parameters for apiCoreKbPermissionBatchPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreKbPermissionBatchPostRequest {
    readonly permissionBatchRequest: PermissionBatchRequest
}

/**
 * Request parameters for apiCoreListFilesGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreListFilesGetRequest {
    readonly limit?: number

    readonly details?: boolean

    readonly alive?: boolean
}

/**
 * Request parameters for apiCoreListFilesInGroupGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreListFilesInGroupGetRequest {
    readonly groupName?: string

    readonly limit?: number

    readonly alive?: boolean
}

/**
 * Request parameters for apiCorePromptsGet operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsGetRequest {
    readonly pageSize?: number

    readonly pageToken?: string
}

/**
 * Request parameters for apiCorePromptsNameDelete operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsNameDeleteRequest {
    readonly name: string
}

/**
 * Request parameters for apiCorePromptsNameGet operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsNameGetRequest {
    readonly name: string
}

/**
 * Request parameters for apiCorePromptsNamePatch operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsNamePatchRequest {
    readonly name: string

    readonly promptPatchRequest: PromptPatchRequest
}

/**
 * Request parameters for apiCorePromptsNameSetDefaultPost operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsNameSetDefaultPostRequest {
    readonly name: string
}

/**
 * Request parameters for apiCorePromptsNameUnsetDefaultPost operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsNameUnsetDefaultPostRequest {
    readonly name: string
}

/**
 * Request parameters for apiCorePromptsPost operation in DefaultApi.
 */
export interface DefaultApiApiCorePromptsPostRequest {
    readonly promptRequest: PromptRequest
}

/**
 * Request parameters for apiCoreStaticFilesPathGet operation in DefaultApi.
 */
export interface DefaultApiApiCoreStaticFilesPathGetRequest {
    readonly path: string
}

/**
 * Request parameters for apiCoreTempUploadsPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreTempUploadsPostRequest {
    readonly files?: Array<File>
}

/**
 * Request parameters for apiCoreUploadFilesPost operation in DefaultApi.
 */
export interface DefaultApiApiCoreUploadFilesPostRequest {
    readonly override?: boolean

    readonly metadatas?: string

    readonly userPath?: string

    readonly files?: Array<File>
}

/**
 * DefaultApi - object-oriented interface
 */
export class DefaultApi extends BaseAPI {
    /**
     * Proxies to parsing service. Multipart form with files.
     * @summary Upload files and add to knowledge base group
     * @param {DefaultApiApiCoreAddFilesToGroupPostRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreAddFilesToGroupPost(requestParameters: DefaultApiApiCoreAddFilesToGroupPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreAddFilesToGroupPost(requestParameters.groupName, requestParameters.override, requestParameters.files, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary Admin (requires document.write)
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreAdminGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreAdminGet(options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary Chat with knowledge base
     * @param {DefaultApiApiCoreChatPostRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreChatPost(requestParameters: DefaultApiApiCoreChatPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreChatPost(requestParameters.apiCoreChatPostRequest, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary Chat with knowledge base (streaming)
     * @param {DefaultApiApiCoreChatStreamPostRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreChatStreamPost(requestParameters: DefaultApiApiCoreChatStreamPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreChatStreamPost(requestParameters.apiCoreChatStreamPostRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationSwitchStatusGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationSwitchStatusGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationSwitchStatusPost(requestParameters: DefaultApiApiCoreConversationSwitchStatusPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationSwitchStatusPost(requestParameters.conversationSwitchStatusRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsChatPost(requestParameters: DefaultApiApiCoreConversationsChatPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsChatPost(requestParameters.body, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsConversationIdStatusGet(requestParameters: DefaultApiApiCoreConversationsConversationIdStatusGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsConversationIdStatusGet(requestParameters.conversationId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsFeedBackChatHistoryPost(requestParameters: DefaultApiApiCoreConversationsFeedBackChatHistoryPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsFeedBackChatHistoryPost(requestParameters.conversationFeedbackRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsGet(requestParameters: DefaultApiApiCoreConversationsGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsGet(requestParameters.keyword, requestParameters.pageSize, requestParameters.pageToken, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsNameDelete(requestParameters: DefaultApiApiCoreConversationsNameDeleteRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsNameDelete(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsNameDetailGet(requestParameters: DefaultApiApiCoreConversationsNameDetailGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsNameDetailGet(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsNameGet(requestParameters: DefaultApiApiCoreConversationsNameGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsNameGet(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsResumeChatPost(requestParameters: DefaultApiApiCoreConversationsResumeChatPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsResumeChatPost(requestParameters.conversationResumeRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsSetChatHistoryPost(requestParameters: DefaultApiApiCoreConversationsSetChatHistoryPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsSetChatHistoryPost(requestParameters.conversationSetHistoryRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreConversationsStopChatGenerationPost(requestParameters: DefaultApiApiCoreConversationsStopChatGenerationPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreConversationsStopChatGenerationPost(requestParameters.conversationStopRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetAlgosGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetAlgosGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetTagsGet(requestParameters: DefaultApiApiCoreDatasetTagsGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetTagsGet(requestParameters.keyword, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetBatchAddMemberPost(requestParameters: DefaultApiApiCoreDatasetsDatasetBatchAddMemberPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetBatchAddMemberPost(requestParameters.dataset, requestParameters.batchAddDatasetMemberRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsDocumentContentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentContentGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentContentGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentDownloadGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentDownloadGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary GET /datasets/{dataset}/documents/{document}/segments
     * @param {DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsGetRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentSegmentsGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary GET /datasets/{dataset}/documents/{document}/segments/{segment}
     * @param {DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGetRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentSegmentsSegmentGet(requestParameters.dataset, requestParameters.document, requestParameters.segment, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetMembersGet(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetMembersGet(requestParameters.dataset, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetMembersSearchPost(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersSearchPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetMembersSearchPost(requestParameters.dataset, requestParameters.searchDatasetMemberRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetMembersUserIdDelete(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdDeleteRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetMembersUserIdDelete(requestParameters.dataset, requestParameters.userId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetMembersUserIdGet(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetMembersUserIdGet(requestParameters.dataset, requestParameters.userId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetMembersUserIdPatch(requestParameters: DefaultApiApiCoreDatasetsDatasetMembersUserIdPatchRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetMembersUserIdPatch(requestParameters.dataset, requestParameters.userId, requestParameters.updateDatasetMemberRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksBatchUploadPost(requestParameters: DefaultApiApiCoreDatasetsDatasetTasksBatchUploadPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetTasksBatchUploadPost(requestParameters.dataset, requestParameters.documentPid, requestParameters.documentTags, requestParameters.files, requestParameters.relativePath, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsPost(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetUploadsPost(requestParameters.dataset, requestParameters.documentPid, requestParameters.documentTags, requestParameters.files, requestParameters.relativePath, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdContentGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetUploadsUploadFileIdContentGet(requestParameters.dataset, requestParameters.uploadFileId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(requestParameters: DefaultApiApiCoreDatasetsDatasetUploadsUploadFileIdDownloadGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDatasetsDatasetUploadsUploadFileIdDownloadGet(requestParameters.dataset, requestParameters.uploadFileId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDocumentCreatorsGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDocumentCreatorsGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDocumentTagsGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreDocumentTagsGet(options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary Health check
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreHealthGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreHealthGet(options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary Hello (requires user.read)
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreHelloGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreHelloGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbGrantPrincipalsGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbGrantPrincipalsGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAclAclIdDelete(requestParameters: DefaultApiApiCoreKbKbIdAclAclIdDeleteRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAclAclIdDelete(requestParameters.kbId, requestParameters.aclId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAclAclIdPut(requestParameters: DefaultApiApiCoreKbKbIdAclAclIdPutRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAclAclIdPut(requestParameters.kbId, requestParameters.aclId, requestParameters.updateACLRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAclBatchPost(requestParameters: DefaultApiApiCoreKbKbIdAclBatchPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAclBatchPost(requestParameters.kbId, requestParameters.batchAddACLRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAclGet(requestParameters: DefaultApiApiCoreKbKbIdAclGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAclGet(requestParameters.kbId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAclPost(requestParameters: DefaultApiApiCoreKbKbIdAclPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAclPost(requestParameters.kbId, requestParameters.addACLRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAuthorizationGet(requestParameters: DefaultApiApiCoreKbKbIdAuthorizationGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAuthorizationGet(requestParameters.kbId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdAuthorizationPost(requestParameters: DefaultApiApiCoreKbKbIdAuthorizationPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdAuthorizationPost(requestParameters.kbId, requestParameters.setKBAuthorizationRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdCanGet(requestParameters: DefaultApiApiCoreKbKbIdCanGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdCanGet(requestParameters.kbId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbKbIdPermissionGet(requestParameters: DefaultApiApiCoreKbKbIdPermissionGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbKbIdPermissionGet(requestParameters.kbId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbListGet(requestParameters: DefaultApiApiCoreKbListGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbListGet(requestParameters.permission, requestParameters.keyword, requestParameters.page, requestParameters.pageSize, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreKbPermissionBatchPost(requestParameters: DefaultApiApiCoreKbPermissionBatchPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreKbPermissionBatchPost(requestParameters.permissionBatchRequest, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * Proxies to parsing service.
     * @summary List files in knowledge base
     * @param {DefaultApiApiCoreListFilesGetRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreListFilesGet(requestParameters: DefaultApiApiCoreListFilesGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreListFilesGet(requestParameters.limit, requestParameters.details, requestParameters.alive, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary List files in a knowledge base group
     * @param {DefaultApiApiCoreListFilesInGroupGetRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreListFilesInGroupGet(requestParameters: DefaultApiApiCoreListFilesInGroupGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreListFilesInGroupGet(requestParameters.groupName, requestParameters.limit, requestParameters.alive, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary List knowledge base groups
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreListKbGroupsGet(options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreListKbGroupsGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsGet(requestParameters: DefaultApiApiCorePromptsGetRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsGet(requestParameters.pageSize, requestParameters.pageToken, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsNameDelete(requestParameters: DefaultApiApiCorePromptsNameDeleteRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsNameDelete(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsNameGet(requestParameters: DefaultApiApiCorePromptsNameGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsNameGet(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsNamePatch(requestParameters: DefaultApiApiCorePromptsNamePatchRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsNamePatch(requestParameters.name, requestParameters.promptPatchRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsNameSetDefaultPost(requestParameters: DefaultApiApiCorePromptsNameSetDefaultPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsNameSetDefaultPost(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsNameUnsetDefaultPost(requestParameters: DefaultApiApiCorePromptsNameUnsetDefaultPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsNameUnsetDefaultPost(requestParameters.name, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCorePromptsPost(requestParameters: DefaultApiApiCorePromptsPostRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCorePromptsPost(requestParameters.promptRequest, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * 
     * @summary GET /static-files/{path:.*}
     * @param {DefaultApiApiCoreStaticFilesPathGetRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreStaticFilesPathGet(requestParameters: DefaultApiApiCoreStaticFilesPathGetRequest, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreStaticFilesPathGet(requestParameters.path, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreTempUploadsPost(requestParameters: DefaultApiApiCoreTempUploadsPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreTempUploadsPost(requestParameters.files, options).then((request) => request(this.axios, this.basePath));
    }

    /**
     * Proxies to parsing service. Multipart form with files.
     * @summary Upload files to knowledge base
     * @param {DefaultApiApiCoreUploadFilesPostRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public apiCoreUploadFilesPost(requestParameters: DefaultApiApiCoreUploadFilesPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DefaultApiFp(this.configuration).apiCoreUploadFilesPost(requestParameters.override, requestParameters.metadatas, requestParameters.userPath, requestParameters.files, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * DocumentsApi - axios parameter creator
 */
export const DocumentsApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        apiCoreDatasetsDatasetBatchDeletePost: async (dataset: string, batchDeleteDocumentRequest: BatchDeleteDocumentRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetBatchDeletePost', 'dataset', dataset)
            // verify required parameter 'batchDeleteDocumentRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetBatchDeletePost', 'batchDeleteDocumentRequest', batchDeleteDocumentRequest)
            const localVarPath = `/api/core/datasets/{dataset}:batchDelete`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(batchDeleteDocumentRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentDelete: async (dataset: string, document: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentDelete', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentDelete', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentGet: async (dataset: string, document: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentGet', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentGet', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentPatch: async (dataset: string, document: string, doc?: Doc, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentPatch', 'dataset', dataset)
            // verify required parameter 'document' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsDocumentPatch', 'document', document)
            const localVarPath = `/api/core/datasets/{dataset}/documents/{document}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"document"}}`, encodeURIComponent(String(document)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(doc, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsGet: async (dataset: string, pageToken?: string, pageSize?: number, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsGet', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/documents`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (pageToken !== undefined) {
                localVarQueryParameter['page_token'] = pageToken;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsPost: async (dataset: string, doc?: Doc, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsPost', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/documents`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(doc, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetDocumentsSearchPost: async (dataset: string, searchDocumentsRequest?: SearchDocumentsRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetDocumentsSearchPost', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/documents:search`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(searchDocumentsRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDocumentsSearchPost: async (searchDocumentsRequest?: SearchDocumentsRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/core/documents:search`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(searchDocumentsRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * DocumentsApi - functional programming interface
 */
export const DocumentsApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = DocumentsApiAxiosParamCreator(configuration)
    return {
        
        async apiCoreDatasetsDatasetBatchDeletePost(dataset: string, batchDeleteDocumentRequest: BatchDeleteDocumentRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetBatchDeletePost(dataset, batchDeleteDocumentRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetBatchDeletePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsDocumentDelete(dataset: string, document: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentDelete(dataset, document, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsDocumentDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsDocumentGet(dataset: string, document: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Doc>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentGet(dataset, document, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsDocumentGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsDocumentPatch(dataset: string, document: string, doc?: Doc, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Doc>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsDocumentPatch(dataset, document, doc, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsDocumentPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsGet(dataset: string, pageToken?: string, pageSize?: number, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDocumentsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsGet(dataset, pageToken, pageSize, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsPost(dataset: string, doc?: Doc, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Doc>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsPost(dataset, doc, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetDocumentsSearchPost(dataset: string, searchDocumentsRequest?: SearchDocumentsRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDocumentsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetDocumentsSearchPost(dataset, searchDocumentsRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDatasetsDatasetDocumentsSearchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDocumentsSearchPost(searchDocumentsRequest?: SearchDocumentsRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListDocumentsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDocumentsSearchPost(searchDocumentsRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['DocumentsApi.apiCoreDocumentsSearchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * DocumentsApi - factory interface
 */
export const DocumentsApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = DocumentsApiFp(configuration)
    return {
        
        apiCoreDatasetsDatasetBatchDeletePost(requestParameters: DocumentsApiApiCoreDatasetsDatasetBatchDeletePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetBatchDeletePost(requestParameters.dataset, requestParameters.batchDeleteDocumentRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentDelete(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentDelete(requestParameters.dataset, requestParameters.document, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentGet(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<Doc> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsDocumentPatch(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<Doc> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsDocumentPatch(requestParameters.dataset, requestParameters.document, requestParameters.doc, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsGet(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListDocumentsResponse> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsGet(requestParameters.dataset, requestParameters.pageToken, requestParameters.pageSize, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsPost(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<Doc> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsPost(requestParameters.dataset, requestParameters.doc, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetDocumentsSearchPost(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsSearchPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListDocumentsResponse> {
            return localVarFp.apiCoreDatasetsDatasetDocumentsSearchPost(requestParameters.dataset, requestParameters.searchDocumentsRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDocumentsSearchPost(requestParameters: DocumentsApiApiCoreDocumentsSearchPostRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<ListDocumentsResponse> {
            return localVarFp.apiCoreDocumentsSearchPost(requestParameters.searchDocumentsRequest, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for apiCoreDatasetsDatasetBatchDeletePost operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetBatchDeletePostRequest {
    readonly dataset: string

    readonly batchDeleteDocumentRequest: BatchDeleteDocumentRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentDelete operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentDeleteRequest {
    readonly dataset: string

    readonly document: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentGet operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentGetRequest {
    readonly dataset: string

    readonly document: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsDocumentPatch operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentPatchRequest {
    readonly dataset: string

    readonly document: string

    readonly doc?: Doc
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsGet operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsGetRequest {
    readonly dataset: string

    readonly pageToken?: string

    readonly pageSize?: number
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsPost operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsPostRequest {
    readonly dataset: string

    readonly doc?: Doc
}

/**
 * Request parameters for apiCoreDatasetsDatasetDocumentsSearchPost operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDatasetsDatasetDocumentsSearchPostRequest {
    readonly dataset: string

    readonly searchDocumentsRequest?: SearchDocumentsRequest
}

/**
 * Request parameters for apiCoreDocumentsSearchPost operation in DocumentsApi.
 */
export interface DocumentsApiApiCoreDocumentsSearchPostRequest {
    readonly searchDocumentsRequest?: SearchDocumentsRequest
}

/**
 * DocumentsApi - object-oriented interface
 */
export class DocumentsApi extends BaseAPI {
    
    public apiCoreDatasetsDatasetBatchDeletePost(requestParameters: DocumentsApiApiCoreDatasetsDatasetBatchDeletePostRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetBatchDeletePost(requestParameters.dataset, requestParameters.batchDeleteDocumentRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsDocumentDelete(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentDeleteRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentDelete(requestParameters.dataset, requestParameters.document, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsDocumentGet(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentGetRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentGet(requestParameters.dataset, requestParameters.document, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsDocumentPatch(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsDocumentPatchRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsDocumentPatch(requestParameters.dataset, requestParameters.document, requestParameters.doc, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsGet(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsGetRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsGet(requestParameters.dataset, requestParameters.pageToken, requestParameters.pageSize, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsPost(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsPostRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsPost(requestParameters.dataset, requestParameters.doc, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetDocumentsSearchPost(requestParameters: DocumentsApiApiCoreDatasetsDatasetDocumentsSearchPostRequest, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDatasetsDatasetDocumentsSearchPost(requestParameters.dataset, requestParameters.searchDocumentsRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDocumentsSearchPost(requestParameters: DocumentsApiApiCoreDocumentsSearchPostRequest = {}, options?: RawAxiosRequestConfig) {
        return DocumentsApiFp(this.configuration).apiCoreDocumentsSearchPost(requestParameters.searchDocumentsRequest, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * TasksApi - axios parameter creator
 */
export const TasksApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        apiCoreDatasetsDatasetTasksGet: async (dataset: string, pageToken?: string, pageSize?: number, taskState?: string, taskType?: string, documentId?: string, documentPid?: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksGet', 'dataset', dataset)
            const localVarPath = `/api/core/datasets/{dataset}/tasks`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            if (pageToken !== undefined) {
                localVarQueryParameter['page_token'] = pageToken;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (taskState !== undefined) {
                localVarQueryParameter['task_state'] = taskState;
            }

            if (taskType !== undefined) {
                localVarQueryParameter['task_type'] = taskType;
            }

            if (documentId !== undefined) {
                localVarQueryParameter['document_id'] = documentId;
            }

            if (documentPid !== undefined) {
                localVarQueryParameter['document_pid'] = documentPid;
            }

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksPost: async (dataset: string, createTaskRequest: CreateTaskRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksPost', 'dataset', dataset)
            // verify required parameter 'createTaskRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksPost', 'createTaskRequest', createTaskRequest)
            const localVarPath = `/api/core/datasets/{dataset}/tasks`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(createTaskRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksSearchPost: async (dataset: string, searchTasksRequest: SearchTasksRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksSearchPost', 'dataset', dataset)
            // verify required parameter 'searchTasksRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksSearchPost', 'searchTasksRequest', searchTasksRequest)
            const localVarPath = `/api/core/datasets/{dataset}/tasks:search`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(searchTasksRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksStartPost: async (dataset: string, startTaskRequest: StartTaskRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksStartPost', 'dataset', dataset)
            // verify required parameter 'startTaskRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksStartPost', 'startTaskRequest', startTaskRequest)
            const localVarPath = `/api/core/datasets/{dataset}/tasks:start`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(startTaskRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksTaskDelete: async (dataset: string, task: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskDelete', 'dataset', dataset)
            // verify required parameter 'task' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskDelete', 'task', task)
            const localVarPath = `/api/core/datasets/{dataset}/tasks/{task}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"task"}}`, encodeURIComponent(String(task)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksTaskGet: async (dataset: string, task: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskGet', 'dataset', dataset)
            // verify required parameter 'task' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskGet', 'task', task)
            const localVarPath = `/api/core/datasets/{dataset}/tasks/{task}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"task"}}`, encodeURIComponent(String(task)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksTaskResumePost: async (dataset: string, task: string, resumeTaskRequest?: ResumeTaskRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskResumePost', 'dataset', dataset)
            // verify required parameter 'task' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskResumePost', 'task', task)
            const localVarPath = `/api/core/datasets/{dataset}/tasks/{task}:resume`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"task"}}`, encodeURIComponent(String(task)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(resumeTaskRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetTasksTaskSuspendPost: async (dataset: string, task: string, suspendJobRequest: SuspendJobRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskSuspendPost', 'dataset', dataset)
            // verify required parameter 'task' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskSuspendPost', 'task', task)
            // verify required parameter 'suspendJobRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetTasksTaskSuspendPost', 'suspendJobRequest', suspendJobRequest)
            const localVarPath = `/api/core/datasets/{dataset}/tasks/{task}:suspend`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"task"}}`, encodeURIComponent(String(task)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(suspendJobRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsInitUploadPost: async (dataset: string, initUploadRequest: InitUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsInitUploadPost', 'dataset', dataset)
            // verify required parameter 'initUploadRequest' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsInitUploadPost', 'initUploadRequest', initUploadRequest)
            const localVarPath = `/api/core/datasets/{dataset}/uploads:initUpload`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(initUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdAbortPost: async (dataset: string, uploadId: string, abortUploadRequest?: AbortUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdAbortPost', 'dataset', dataset)
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdAbortPost', 'uploadId', uploadId)
            const localVarPath = `/api/core/datasets/{dataset}/uploads/{upload_id}:abort`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(abortUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdCompletePost: async (dataset: string, uploadId: string, completeUploadRequest?: CompleteUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdCompletePost', 'dataset', dataset)
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdCompletePost', 'uploadId', uploadId)
            const localVarPath = `/api/core/datasets/{dataset}/uploads/{upload_id}:complete`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(completeUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut: async (dataset: string, uploadId: string, partNumber: string, body: File, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'dataset' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut', 'dataset', dataset)
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut', 'uploadId', uploadId)
            // verify required parameter 'partNumber' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut', 'partNumber', partNumber)
            // verify required parameter 'body' is not null or undefined
            assertParamExists('apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut', 'body', body)
            const localVarPath = `/api/core/datasets/{dataset}/uploads/{upload_id}/parts/{part_number}`
                .replace(`{${"dataset"}}`, encodeURIComponent(String(dataset)))
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)))
                .replace(`{${"part_number"}}`, encodeURIComponent(String(partNumber)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PUT', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/octet-stream';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(body, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * TasksApi - functional programming interface
 */
export const TasksApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = TasksApiAxiosParamCreator(configuration)
    return {
        
        async apiCoreDatasetsDatasetTasksGet(dataset: string, pageToken?: string, pageSize?: number, taskState?: string, taskType?: string, documentId?: string, documentPid?: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksGet(dataset, pageToken, pageSize, taskState, taskType, documentId, documentPid, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksPost(dataset: string, createTaskRequest: CreateTaskRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<CreateTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksPost(dataset, createTaskRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksSearchPost(dataset: string, searchTasksRequest: SearchTasksRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ListTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksSearchPost(dataset, searchTasksRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksSearchPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksStartPost(dataset: string, startTaskRequest: StartTaskRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<StartTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksStartPost(dataset, startTaskRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksStartPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksTaskDelete(dataset: string, task: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksTaskDelete(dataset, task, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksTaskDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksTaskGet(dataset: string, task: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<TaskResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksTaskGet(dataset, task, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksTaskGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksTaskResumePost(dataset: string, task: string, resumeTaskRequest?: ResumeTaskRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<StartTasksResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksTaskResumePost(dataset, task, resumeTaskRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksTaskResumePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetTasksTaskSuspendPost(dataset: string, task: string, suspendJobRequest: SuspendJobRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<object>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetTasksTaskSuspendPost(dataset, task, suspendJobRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetTasksTaskSuspendPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsInitUploadPost(dataset: string, initUploadRequest: InitUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<InitUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsInitUploadPost(dataset, initUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetUploadsInitUploadPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsUploadIdAbortPost(dataset: string, uploadId: string, abortUploadRequest?: AbortUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<AbortUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsUploadIdAbortPost(dataset, uploadId, abortUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetUploadsUploadIdAbortPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsUploadIdCompletePost(dataset: string, uploadId: string, completeUploadRequest?: CompleteUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<CompleteUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsUploadIdCompletePost(dataset, uploadId, completeUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetUploadsUploadIdCompletePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(dataset: string, uploadId: string, partNumber: string, body: File, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UploadPartResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(dataset, uploadId, partNumber, body, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['TasksApi.apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * TasksApi - factory interface
 */
export const TasksApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = TasksApiFp(configuration)
    return {
        
        apiCoreDatasetsDatasetTasksGet(requestParameters: TasksApiApiCoreDatasetsDatasetTasksGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksGet(requestParameters.dataset, requestParameters.pageToken, requestParameters.pageSize, requestParameters.taskState, requestParameters.taskType, requestParameters.documentId, requestParameters.documentPid, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<CreateTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksPost(requestParameters.dataset, requestParameters.createTaskRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksSearchPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksSearchPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<ListTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksSearchPost(requestParameters.dataset, requestParameters.searchTasksRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksStartPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksStartPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<StartTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksStartPost(requestParameters.dataset, requestParameters.startTaskRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksTaskDelete(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetTasksTaskDelete(requestParameters.dataset, requestParameters.task, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksTaskGet(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<TaskResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksTaskGet(requestParameters.dataset, requestParameters.task, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksTaskResumePost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskResumePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<StartTasksResponse> {
            return localVarFp.apiCoreDatasetsDatasetTasksTaskResumePost(requestParameters.dataset, requestParameters.task, requestParameters.resumeTaskRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetTasksTaskSuspendPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskSuspendPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<object> {
            return localVarFp.apiCoreDatasetsDatasetTasksTaskSuspendPost(requestParameters.dataset, requestParameters.task, requestParameters.suspendJobRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsInitUploadPost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsInitUploadPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<InitUploadResponse> {
            return localVarFp.apiCoreDatasetsDatasetUploadsInitUploadPost(requestParameters.dataset, requestParameters.initUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdAbortPost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdAbortPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<AbortUploadResponse> {
            return localVarFp.apiCoreDatasetsDatasetUploadsUploadIdAbortPost(requestParameters.dataset, requestParameters.uploadId, requestParameters.abortUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdCompletePost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdCompletePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<CompleteUploadResponse> {
            return localVarFp.apiCoreDatasetsDatasetUploadsUploadIdCompletePost(requestParameters.dataset, requestParameters.uploadId, requestParameters.completeUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPutRequest, options?: RawAxiosRequestConfig): AxiosPromise<UploadPartResponse> {
            return localVarFp.apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(requestParameters.dataset, requestParameters.uploadId, requestParameters.partNumber, requestParameters.body, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for apiCoreDatasetsDatasetTasksGet operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksGetRequest {
    readonly dataset: string

    readonly pageToken?: string

    readonly pageSize?: number

    readonly taskState?: string

    readonly taskType?: string

    readonly documentId?: string

    readonly documentPid?: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksPostRequest {
    readonly dataset: string

    readonly createTaskRequest: CreateTaskRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksSearchPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksSearchPostRequest {
    readonly dataset: string

    readonly searchTasksRequest: SearchTasksRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksStartPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksStartPostRequest {
    readonly dataset: string

    readonly startTaskRequest: StartTaskRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksTaskDelete operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksTaskDeleteRequest {
    readonly dataset: string

    readonly task: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksTaskGet operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksTaskGetRequest {
    readonly dataset: string

    readonly task: string
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksTaskResumePost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksTaskResumePostRequest {
    readonly dataset: string

    readonly task: string

    readonly resumeTaskRequest?: ResumeTaskRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetTasksTaskSuspendPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetTasksTaskSuspendPostRequest {
    readonly dataset: string

    readonly task: string

    readonly suspendJobRequest: SuspendJobRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsInitUploadPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetUploadsInitUploadPostRequest {
    readonly dataset: string

    readonly initUploadRequest: InitUploadRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsUploadIdAbortPost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetUploadsUploadIdAbortPostRequest {
    readonly dataset: string

    readonly uploadId: string

    readonly abortUploadRequest?: AbortUploadRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsUploadIdCompletePost operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetUploadsUploadIdCompletePostRequest {
    readonly dataset: string

    readonly uploadId: string

    readonly completeUploadRequest?: CompleteUploadRequest
}

/**
 * Request parameters for apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut operation in TasksApi.
 */
export interface TasksApiApiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPutRequest {
    readonly dataset: string

    readonly uploadId: string

    readonly partNumber: string

    readonly body: File
}

/**
 * TasksApi - object-oriented interface
 */
export class TasksApi extends BaseAPI {
    
    public apiCoreDatasetsDatasetTasksGet(requestParameters: TasksApiApiCoreDatasetsDatasetTasksGetRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksGet(requestParameters.dataset, requestParameters.pageToken, requestParameters.pageSize, requestParameters.taskState, requestParameters.taskType, requestParameters.documentId, requestParameters.documentPid, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksPost(requestParameters.dataset, requestParameters.createTaskRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksSearchPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksSearchPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksSearchPost(requestParameters.dataset, requestParameters.searchTasksRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksStartPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksStartPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksStartPost(requestParameters.dataset, requestParameters.startTaskRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksTaskDelete(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskDeleteRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksTaskDelete(requestParameters.dataset, requestParameters.task, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksTaskGet(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskGetRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksTaskGet(requestParameters.dataset, requestParameters.task, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksTaskResumePost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskResumePostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksTaskResumePost(requestParameters.dataset, requestParameters.task, requestParameters.resumeTaskRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetTasksTaskSuspendPost(requestParameters: TasksApiApiCoreDatasetsDatasetTasksTaskSuspendPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetTasksTaskSuspendPost(requestParameters.dataset, requestParameters.task, requestParameters.suspendJobRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsInitUploadPost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsInitUploadPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetUploadsInitUploadPost(requestParameters.dataset, requestParameters.initUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsUploadIdAbortPost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdAbortPostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetUploadsUploadIdAbortPost(requestParameters.dataset, requestParameters.uploadId, requestParameters.abortUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsUploadIdCompletePost(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdCompletePostRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetUploadsUploadIdCompletePost(requestParameters.dataset, requestParameters.uploadId, requestParameters.completeUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(requestParameters: TasksApiApiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPutRequest, options?: RawAxiosRequestConfig) {
        return TasksApiFp(this.configuration).apiCoreDatasetsDatasetUploadsUploadIdPartsPartNumberPut(requestParameters.dataset, requestParameters.uploadId, requestParameters.partNumber, requestParameters.body, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * UploadsApi - axios parameter creator
 */
export const UploadsApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        apiCoreTempUploadsInitUploadPost: async (initUploadRequest: InitUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'initUploadRequest' is not null or undefined
            assertParamExists('apiCoreTempUploadsInitUploadPost', 'initUploadRequest', initUploadRequest)
            const localVarPath = `/api/core/temp/uploads:initUpload`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(initUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreTempUploadsUploadIdAbortPost: async (uploadId: string, abortUploadRequest?: AbortUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreTempUploadsUploadIdAbortPost', 'uploadId', uploadId)
            const localVarPath = `/api/core/temp/uploads/{upload_id}:abort`
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(abortUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreTempUploadsUploadIdCompletePost: async (uploadId: string, completeUploadRequest?: CompleteUploadRequest, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreTempUploadsUploadIdCompletePost', 'uploadId', uploadId)
            const localVarPath = `/api/core/temp/uploads/{upload_id}:complete`
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(completeUploadRequest, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        apiCoreTempUploadsUploadIdPartsPartNumberPut: async (uploadId: string, partNumber: string, body: File, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'uploadId' is not null or undefined
            assertParamExists('apiCoreTempUploadsUploadIdPartsPartNumberPut', 'uploadId', uploadId)
            // verify required parameter 'partNumber' is not null or undefined
            assertParamExists('apiCoreTempUploadsUploadIdPartsPartNumberPut', 'partNumber', partNumber)
            // verify required parameter 'body' is not null or undefined
            assertParamExists('apiCoreTempUploadsUploadIdPartsPartNumberPut', 'body', body)
            const localVarPath = `/api/core/temp/uploads/{upload_id}/parts/{part_number}`
                .replace(`{${"upload_id"}}`, encodeURIComponent(String(uploadId)))
                .replace(`{${"part_number"}}`, encodeURIComponent(String(partNumber)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PUT', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            localVarHeaderParameter['Content-Type'] = 'application/octet-stream';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(body, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * UploadsApi - functional programming interface
 */
export const UploadsApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = UploadsApiAxiosParamCreator(configuration)
    return {
        
        async apiCoreTempUploadsInitUploadPost(initUploadRequest: InitUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<InitUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreTempUploadsInitUploadPost(initUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UploadsApi.apiCoreTempUploadsInitUploadPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreTempUploadsUploadIdAbortPost(uploadId: string, abortUploadRequest?: AbortUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<AbortUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreTempUploadsUploadIdAbortPost(uploadId, abortUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UploadsApi.apiCoreTempUploadsUploadIdAbortPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreTempUploadsUploadIdCompletePost(uploadId: string, completeUploadRequest?: CompleteUploadRequest, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<CompleteUploadResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreTempUploadsUploadIdCompletePost(uploadId, completeUploadRequest, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UploadsApi.apiCoreTempUploadsUploadIdCompletePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async apiCoreTempUploadsUploadIdPartsPartNumberPut(uploadId: string, partNumber: string, body: File, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UploadPartResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.apiCoreTempUploadsUploadIdPartsPartNumberPut(uploadId, partNumber, body, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UploadsApi.apiCoreTempUploadsUploadIdPartsPartNumberPut']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * UploadsApi - factory interface
 */
export const UploadsApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = UploadsApiFp(configuration)
    return {
        
        apiCoreTempUploadsInitUploadPost(requestParameters: UploadsApiApiCoreTempUploadsInitUploadPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<InitUploadResponse> {
            return localVarFp.apiCoreTempUploadsInitUploadPost(requestParameters.initUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreTempUploadsUploadIdAbortPost(requestParameters: UploadsApiApiCoreTempUploadsUploadIdAbortPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<AbortUploadResponse> {
            return localVarFp.apiCoreTempUploadsUploadIdAbortPost(requestParameters.uploadId, requestParameters.abortUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreTempUploadsUploadIdCompletePost(requestParameters: UploadsApiApiCoreTempUploadsUploadIdCompletePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<CompleteUploadResponse> {
            return localVarFp.apiCoreTempUploadsUploadIdCompletePost(requestParameters.uploadId, requestParameters.completeUploadRequest, options).then((request) => request(axios, basePath));
        },
        
        apiCoreTempUploadsUploadIdPartsPartNumberPut(requestParameters: UploadsApiApiCoreTempUploadsUploadIdPartsPartNumberPutRequest, options?: RawAxiosRequestConfig): AxiosPromise<UploadPartResponse> {
            return localVarFp.apiCoreTempUploadsUploadIdPartsPartNumberPut(requestParameters.uploadId, requestParameters.partNumber, requestParameters.body, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for apiCoreTempUploadsInitUploadPost operation in UploadsApi.
 */
export interface UploadsApiApiCoreTempUploadsInitUploadPostRequest {
    readonly initUploadRequest: InitUploadRequest
}

/**
 * Request parameters for apiCoreTempUploadsUploadIdAbortPost operation in UploadsApi.
 */
export interface UploadsApiApiCoreTempUploadsUploadIdAbortPostRequest {
    readonly uploadId: string

    readonly abortUploadRequest?: AbortUploadRequest
}

/**
 * Request parameters for apiCoreTempUploadsUploadIdCompletePost operation in UploadsApi.
 */
export interface UploadsApiApiCoreTempUploadsUploadIdCompletePostRequest {
    readonly uploadId: string

    readonly completeUploadRequest?: CompleteUploadRequest
}

/**
 * Request parameters for apiCoreTempUploadsUploadIdPartsPartNumberPut operation in UploadsApi.
 */
export interface UploadsApiApiCoreTempUploadsUploadIdPartsPartNumberPutRequest {
    readonly uploadId: string

    readonly partNumber: string

    readonly body: File
}

/**
 * UploadsApi - object-oriented interface
 */
export class UploadsApi extends BaseAPI {
    
    public apiCoreTempUploadsInitUploadPost(requestParameters: UploadsApiApiCoreTempUploadsInitUploadPostRequest, options?: RawAxiosRequestConfig) {
        return UploadsApiFp(this.configuration).apiCoreTempUploadsInitUploadPost(requestParameters.initUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreTempUploadsUploadIdAbortPost(requestParameters: UploadsApiApiCoreTempUploadsUploadIdAbortPostRequest, options?: RawAxiosRequestConfig) {
        return UploadsApiFp(this.configuration).apiCoreTempUploadsUploadIdAbortPost(requestParameters.uploadId, requestParameters.abortUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreTempUploadsUploadIdCompletePost(requestParameters: UploadsApiApiCoreTempUploadsUploadIdCompletePostRequest, options?: RawAxiosRequestConfig) {
        return UploadsApiFp(this.configuration).apiCoreTempUploadsUploadIdCompletePost(requestParameters.uploadId, requestParameters.completeUploadRequest, options).then((request) => request(this.axios, this.basePath));
    }

    
    public apiCoreTempUploadsUploadIdPartsPartNumberPut(requestParameters: UploadsApiApiCoreTempUploadsUploadIdPartsPartNumberPutRequest, options?: RawAxiosRequestConfig) {
        return UploadsApiFp(this.configuration).apiCoreTempUploadsUploadIdPartsPartNumberPut(requestParameters.uploadId, requestParameters.partNumber, requestParameters.body, options).then((request) => request(this.axios, this.basePath));
    }
}



