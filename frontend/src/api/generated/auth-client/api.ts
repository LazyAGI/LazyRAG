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

export interface AuthorizeBody {
    'method': string;
    'path': string;
}

export interface AuthorizeResponse {
    'allowed': boolean;
}
export interface ChangePasswordBody {
    'old_password': string;
    'new_password': string;
}
export interface CreateUserBody {
    'username': string;
    'password': string;
    'role_id'?: string | null;
    'email'?: string | null;
    'tenant_id'?: string;
    'disabled'?: boolean;
}
export interface CreateUserResponse {
    'user_id': string;
    'username': string;
    'role_id': string;
    'role_name': string;
}
export interface GroupAddUsersBody {
    'user_ids': Array<string>;
    'role'?: string | null;
}
export interface GroupCreateBody {
    'group_name': string;
    'remark'?: string | null;
    'tenant_id'?: string | null;
}

export interface GroupCreateResponse {
    'group_id': string;
}

export interface GroupDetailResponse {
    'group_id': string;
    'group_name': string;
    'remark'?: string | null;
    'tenant_id'?: string | null;
}

export interface GroupItem {
    'group_id': string;
    'group_name': string;
    'remark'?: string | null;
    'tenant_id'?: string | null;
}

export interface GroupListResponse {
    'groups': Array<GroupItem>;
    'total': number;
    'page': number;
    'page_size': number;
}

export interface GroupMemberRoleBatchBody {
    'user_ids': Array<string>;
    'role': string;
}

export interface GroupPermissionsBody {
    'permission_groups': Array<string>;
}

export interface GroupPermissionsResponse {
    'permission_groups': Array<string>;
}
export interface GroupRemoveUsersBody {
    'user_ids': Array<string>;
}
export interface GroupUpdateBody {
    'group_name'?: string | null;
    'remark'?: string | null;
    'tenant_id'?: string | null;
}

export interface GroupUserItem {
    'user_id': string;
    'username': string;
    'role': string;
    'tenant_id'?: string | null;
}

export interface GroupUserListResponse {
    'users': Array<GroupUserItem>;
}
export interface HTTPValidationError {
    'detail'?: Array<ValidationError>;
}

export interface HealthResponse {
    'status'?: string;
    'timestamp': number;
}
export interface LocationInner {
}
export interface LoginBody {
    'username': string;
    'password': string;
}

export interface LoginResponse {
    'access_token': string;
    'refresh_token': string;
    'token_type'?: string;
    'role': string;
    'expires_in': number;
    'tenant_id'?: string | null;
}
export interface LogoutBody {
    'refresh_token'?: string | null;
}

export interface MeResponse {
    'user_id': string;
    'username': string;
    'display_name'?: string;
    'email'?: string | null;
    'status': string;
    'role': string;
    'permissions': Array<string>;
    'tenant_id'?: string | null;
}

export interface OkResponse {
    'ok'?: boolean;
}

export interface PermissionGroupItem {
    'id': string;
    'code': string;
    'description'?: string;
    'module'?: string;
    'action'?: string;
}
export interface RefreshBody {
    'refresh_token': string;
}
export interface RegisterBody {
    'username': string;
    'password': string;
    'confirm_password': string;
    'email'?: string | null;
    'tenant_id'?: string | null;
}

export interface RegisterResponse {
    'success'?: boolean;
    'user_id': string;
    'tenant_id'?: string | null;
    'role': string;
}
export interface ResetPasswordBody {
    'new_password': string;
}
export interface RoleCreateBody {
    'name': string;
}

export interface RoleCreateResponse {
    'id': string;
    'name': string;
    'built_in': boolean;
}

export interface RoleItem {
    'id': string;
    'name': string;
    'built_in': boolean;
}
export interface RolePermissionsBody {
    'permission_groups': Array<string>;
}

export interface RolePermissionsResponse {
    'role_id': string;
    'permission_groups': Array<string>;
}

export interface SuccessResponse {
    'success'?: boolean;
}

export interface UserDetailResponse {
    'user_id': string;
    'username': string;
    'display_name'?: string;
    'email'?: string | null;
    'phone'?: string | null;
    'status': string;
    'tenant_id'?: string | null;
    'role_id': string;
    'role_name': string;
}

export interface UserItem {
    'user_id': string;
    'username': string;
    'display_name'?: string;
    'email'?: string | null;
    'phone'?: string | null;
    'status': string;
    'tenant_id'?: string | null;
    'role_id': string;
    'role_name': string;
}

export interface UserListResponse {
    'users': Array<UserItem>;
    'total': number;
    'page': number;
    'page_size': number;
}

export interface UserRoleBatchBody {
    'user_ids': Array<string>;
    'role_id': string;
}
export interface UserRoleBody {
    'role_id': string;
}

export interface ValidateResponse {
    'sub': string;
    'role': string;
    'tenant_id'?: string | null;
    'permissions': Array<string>;
}
export interface ValidationError {
    'loc': Array<LocationInner>;
    'msg': string;
    'type': string;
}

/**
 * AuthApi - axios parameter creator
 */
export const AuthApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        changePasswordApiAuthserviceAuthChangePasswordPost: async (changePasswordBody: ChangePasswordBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'changePasswordBody' is not null or undefined
            assertParamExists('changePasswordApiAuthserviceAuthChangePasswordPost', 'changePasswordBody', changePasswordBody)
            const localVarPath = `/api/authservice/auth/change_password`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(changePasswordBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        healthApiAuthserviceAuthHealthGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/auth/health`;
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
        
        loginApiAuthserviceAuthLoginPost: async (loginBody: LoginBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'loginBody' is not null or undefined
            assertParamExists('loginApiAuthserviceAuthLoginPost', 'loginBody', loginBody)
            const localVarPath = `/api/authservice/auth/login`;
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
            localVarRequestOptions.data = serializeDataIfNeeded(loginBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        logoutApiAuthserviceAuthLogoutPost: async (logoutBody: LogoutBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'logoutBody' is not null or undefined
            assertParamExists('logoutApiAuthserviceAuthLogoutPost', 'logoutBody', logoutBody)
            const localVarPath = `/api/authservice/auth/logout`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(logoutBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        meApiAuthserviceAuthMeGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/auth/me`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        refreshApiAuthserviceAuthRefreshPost: async (refreshBody: RefreshBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'refreshBody' is not null or undefined
            assertParamExists('refreshApiAuthserviceAuthRefreshPost', 'refreshBody', refreshBody)
            const localVarPath = `/api/authservice/auth/refresh`;
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
            localVarRequestOptions.data = serializeDataIfNeeded(refreshBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        registerApiAuthserviceAuthRegisterPost: async (registerBody: RegisterBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'registerBody' is not null or undefined
            assertParamExists('registerApiAuthserviceAuthRegisterPost', 'registerBody', registerBody)
            const localVarPath = `/api/authservice/auth/register`;
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
            localVarRequestOptions.data = serializeDataIfNeeded(registerBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        validateApiAuthserviceAuthValidatePost: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/auth/validate`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * AuthApi - functional programming interface
 */
export const AuthApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = AuthApiAxiosParamCreator(configuration)
    return {
        
        async changePasswordApiAuthserviceAuthChangePasswordPost(changePasswordBody: ChangePasswordBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<SuccessResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.changePasswordApiAuthserviceAuthChangePasswordPost(changePasswordBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.changePasswordApiAuthserviceAuthChangePasswordPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async healthApiAuthserviceAuthHealthGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<HealthResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.healthApiAuthserviceAuthHealthGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.healthApiAuthserviceAuthHealthGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async loginApiAuthserviceAuthLoginPost(loginBody: LoginBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<LoginResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.loginApiAuthserviceAuthLoginPost(loginBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.loginApiAuthserviceAuthLoginPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async logoutApiAuthserviceAuthLogoutPost(logoutBody: LogoutBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<SuccessResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.logoutApiAuthserviceAuthLogoutPost(logoutBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.logoutApiAuthserviceAuthLogoutPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async meApiAuthserviceAuthMeGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<MeResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.meApiAuthserviceAuthMeGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.meApiAuthserviceAuthMeGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async refreshApiAuthserviceAuthRefreshPost(refreshBody: RefreshBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<LoginResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.refreshApiAuthserviceAuthRefreshPost(refreshBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.refreshApiAuthserviceAuthRefreshPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async registerApiAuthserviceAuthRegisterPost(registerBody: RegisterBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<RegisterResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.registerApiAuthserviceAuthRegisterPost(registerBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.registerApiAuthserviceAuthRegisterPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async validateApiAuthserviceAuthValidatePost(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<ValidateResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.validateApiAuthserviceAuthValidatePost(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthApi.validateApiAuthserviceAuthValidatePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * AuthApi - factory interface
 */
export const AuthApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = AuthApiFp(configuration)
    return {
        
        changePasswordApiAuthserviceAuthChangePasswordPost(requestParameters: AuthApiChangePasswordApiAuthserviceAuthChangePasswordPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<SuccessResponse> {
            return localVarFp.changePasswordApiAuthserviceAuthChangePasswordPost(requestParameters.changePasswordBody, options).then((request) => request(axios, basePath));
        },
        
        healthApiAuthserviceAuthHealthGet(options?: RawAxiosRequestConfig): AxiosPromise<HealthResponse> {
            return localVarFp.healthApiAuthserviceAuthHealthGet(options).then((request) => request(axios, basePath));
        },
        
        loginApiAuthserviceAuthLoginPost(requestParameters: AuthApiLoginApiAuthserviceAuthLoginPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<LoginResponse> {
            return localVarFp.loginApiAuthserviceAuthLoginPost(requestParameters.loginBody, options).then((request) => request(axios, basePath));
        },
        
        logoutApiAuthserviceAuthLogoutPost(requestParameters: AuthApiLogoutApiAuthserviceAuthLogoutPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<SuccessResponse> {
            return localVarFp.logoutApiAuthserviceAuthLogoutPost(requestParameters.logoutBody, options).then((request) => request(axios, basePath));
        },
        
        meApiAuthserviceAuthMeGet(options?: RawAxiosRequestConfig): AxiosPromise<MeResponse> {
            return localVarFp.meApiAuthserviceAuthMeGet(options).then((request) => request(axios, basePath));
        },
        
        refreshApiAuthserviceAuthRefreshPost(requestParameters: AuthApiRefreshApiAuthserviceAuthRefreshPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<LoginResponse> {
            return localVarFp.refreshApiAuthserviceAuthRefreshPost(requestParameters.refreshBody, options).then((request) => request(axios, basePath));
        },
        
        registerApiAuthserviceAuthRegisterPost(requestParameters: AuthApiRegisterApiAuthserviceAuthRegisterPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<RegisterResponse> {
            return localVarFp.registerApiAuthserviceAuthRegisterPost(requestParameters.registerBody, options).then((request) => request(axios, basePath));
        },
        
        validateApiAuthserviceAuthValidatePost(options?: RawAxiosRequestConfig): AxiosPromise<ValidateResponse> {
            return localVarFp.validateApiAuthserviceAuthValidatePost(options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for changePasswordApiAuthserviceAuthChangePasswordPost operation in AuthApi.
 */
export interface AuthApiChangePasswordApiAuthserviceAuthChangePasswordPostRequest {
    readonly changePasswordBody: ChangePasswordBody
}

/**
 * Request parameters for loginApiAuthserviceAuthLoginPost operation in AuthApi.
 */
export interface AuthApiLoginApiAuthserviceAuthLoginPostRequest {
    readonly loginBody: LoginBody
}

/**
 * Request parameters for logoutApiAuthserviceAuthLogoutPost operation in AuthApi.
 */
export interface AuthApiLogoutApiAuthserviceAuthLogoutPostRequest {
    readonly logoutBody: LogoutBody
}

/**
 * Request parameters for refreshApiAuthserviceAuthRefreshPost operation in AuthApi.
 */
export interface AuthApiRefreshApiAuthserviceAuthRefreshPostRequest {
    readonly refreshBody: RefreshBody
}

/**
 * Request parameters for registerApiAuthserviceAuthRegisterPost operation in AuthApi.
 */
export interface AuthApiRegisterApiAuthserviceAuthRegisterPostRequest {
    readonly registerBody: RegisterBody
}

/**
 * AuthApi - object-oriented interface
 */
export class AuthApi extends BaseAPI {
    
    public changePasswordApiAuthserviceAuthChangePasswordPost(requestParameters: AuthApiChangePasswordApiAuthserviceAuthChangePasswordPostRequest, options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).changePasswordApiAuthserviceAuthChangePasswordPost(requestParameters.changePasswordBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public healthApiAuthserviceAuthHealthGet(options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).healthApiAuthserviceAuthHealthGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public loginApiAuthserviceAuthLoginPost(requestParameters: AuthApiLoginApiAuthserviceAuthLoginPostRequest, options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).loginApiAuthserviceAuthLoginPost(requestParameters.loginBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public logoutApiAuthserviceAuthLogoutPost(requestParameters: AuthApiLogoutApiAuthserviceAuthLogoutPostRequest, options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).logoutApiAuthserviceAuthLogoutPost(requestParameters.logoutBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public meApiAuthserviceAuthMeGet(options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).meApiAuthserviceAuthMeGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public refreshApiAuthserviceAuthRefreshPost(requestParameters: AuthApiRefreshApiAuthserviceAuthRefreshPostRequest, options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).refreshApiAuthserviceAuthRefreshPost(requestParameters.refreshBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public registerApiAuthserviceAuthRegisterPost(requestParameters: AuthApiRegisterApiAuthserviceAuthRegisterPostRequest, options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).registerApiAuthserviceAuthRegisterPost(requestParameters.registerBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public validateApiAuthserviceAuthValidatePost(options?: RawAxiosRequestConfig) {
        return AuthApiFp(this.configuration).validateApiAuthserviceAuthValidatePost(options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * AuthorizationApi - axios parameter creator
 */
export const AuthorizationApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        authorizeApiAuthserviceAuthAuthorizePost: async (authorizeBody: AuthorizeBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'authorizeBody' is not null or undefined
            assertParamExists('authorizeApiAuthserviceAuthAuthorizePost', 'authorizeBody', authorizeBody)
            const localVarPath = `/api/authservice/auth/authorize`;
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
            localVarRequestOptions.data = serializeDataIfNeeded(authorizeBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * AuthorizationApi - functional programming interface
 */
export const AuthorizationApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = AuthorizationApiAxiosParamCreator(configuration)
    return {
        
        async authorizeApiAuthserviceAuthAuthorizePost(authorizeBody: AuthorizeBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<AuthorizeResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.authorizeApiAuthserviceAuthAuthorizePost(authorizeBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['AuthorizationApi.authorizeApiAuthserviceAuthAuthorizePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * AuthorizationApi - factory interface
 */
export const AuthorizationApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = AuthorizationApiFp(configuration)
    return {
        
        authorizeApiAuthserviceAuthAuthorizePost(requestParameters: AuthorizationApiAuthorizeApiAuthserviceAuthAuthorizePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<AuthorizeResponse> {
            return localVarFp.authorizeApiAuthserviceAuthAuthorizePost(requestParameters.authorizeBody, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for authorizeApiAuthserviceAuthAuthorizePost operation in AuthorizationApi.
 */
export interface AuthorizationApiAuthorizeApiAuthserviceAuthAuthorizePostRequest {
    readonly authorizeBody: AuthorizeBody
}

/**
 * AuthorizationApi - object-oriented interface
 */
export class AuthorizationApi extends BaseAPI {
    
    public authorizeApiAuthserviceAuthAuthorizePost(requestParameters: AuthorizationApiAuthorizeApiAuthserviceAuthAuthorizePostRequest, options?: RawAxiosRequestConfig) {
        return AuthorizationApiFp(this.configuration).authorizeApiAuthserviceAuthAuthorizePost(requestParameters.authorizeBody, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * GroupApi - axios parameter creator
 */
export const GroupApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        addGroupUsersApiAuthserviceGroupGroupIdUserPost: async (groupId: string, groupAddUsersBody: GroupAddUsersBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('addGroupUsersApiAuthserviceGroupGroupIdUserPost', 'groupId', groupId)
            // verify required parameter 'groupAddUsersBody' is not null or undefined
            assertParamExists('addGroupUsersApiAuthserviceGroupGroupIdUserPost', 'groupAddUsersBody', groupAddUsersBody)
            const localVarPath = `/api/authservice/group/{group_id}/user`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupAddUsersBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        createGroupApiAuthserviceGroupPost: async (groupCreateBody: GroupCreateBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupCreateBody' is not null or undefined
            assertParamExists('createGroupApiAuthserviceGroupPost', 'groupCreateBody', groupCreateBody)
            const localVarPath = `/api/authservice/group`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupCreateBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        deleteGroupApiAuthserviceGroupGroupIdDelete: async (groupId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('deleteGroupApiAuthserviceGroupGroupIdDelete', 'groupId', groupId)
            const localVarPath = `/api/authservice/group/{group_id}`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        getGroupApiAuthserviceGroupGroupIdGet: async (groupId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('getGroupApiAuthserviceGroupGroupIdGet', 'groupId', groupId)
            const localVarPath = `/api/authservice/group/{group_id}`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet: async (groupId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet', 'groupId', groupId)
            const localVarPath = `/api/authservice/group/{group_id}/permissions`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        listGroupUsersApiAuthserviceGroupGroupIdUserGet: async (groupId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('listGroupUsersApiAuthserviceGroupGroupIdUserGet', 'groupId', groupId)
            const localVarPath = `/api/authservice/group/{group_id}/user`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        listGroupsApiAuthserviceGroupGet: async (page?: number, pageSize?: number, search?: string | null, tenantId?: string | null, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/group`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            if (page !== undefined) {
                localVarQueryParameter['page'] = page;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (search !== undefined) {
                localVarQueryParameter['search'] = search;
            }

            if (tenantId !== undefined) {
                localVarQueryParameter['tenant_id'] = tenantId;
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
        
        removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost: async (groupId: string, groupRemoveUsersBody: GroupRemoveUsersBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost', 'groupId', groupId)
            // verify required parameter 'groupRemoveUsersBody' is not null or undefined
            assertParamExists('removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost', 'groupRemoveUsersBody', groupRemoveUsersBody)
            const localVarPath = `/api/authservice/group/{group_id}/user/remove`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupRemoveUsersBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut: async (groupId: string, groupPermissionsBody: GroupPermissionsBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut', 'groupId', groupId)
            // verify required parameter 'groupPermissionsBody' is not null or undefined
            assertParamExists('setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut', 'groupPermissionsBody', groupPermissionsBody)
            const localVarPath = `/api/authservice/group/{group_id}/permissions`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PUT', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupPermissionsBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch: async (groupId: string, groupMemberRoleBatchBody: GroupMemberRoleBatchBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch', 'groupId', groupId)
            // verify required parameter 'groupMemberRoleBatchBody' is not null or undefined
            assertParamExists('setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch', 'groupMemberRoleBatchBody', groupMemberRoleBatchBody)
            const localVarPath = `/api/authservice/group/{group_id}/user/role`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupMemberRoleBatchBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        updateGroupApiAuthserviceGroupGroupIdPatch: async (groupId: string, groupUpdateBody: GroupUpdateBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'groupId' is not null or undefined
            assertParamExists('updateGroupApiAuthserviceGroupGroupIdPatch', 'groupId', groupId)
            // verify required parameter 'groupUpdateBody' is not null or undefined
            assertParamExists('updateGroupApiAuthserviceGroupGroupIdPatch', 'groupUpdateBody', groupUpdateBody)
            const localVarPath = `/api/authservice/group/{group_id}`
                .replace(`{${"group_id"}}`, encodeURIComponent(String(groupId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(groupUpdateBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * GroupApi - functional programming interface
 */
export const GroupApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = GroupApiAxiosParamCreator(configuration)
    return {
        
        async addGroupUsersApiAuthserviceGroupGroupIdUserPost(groupId: string, groupAddUsersBody: GroupAddUsersBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.addGroupUsersApiAuthserviceGroupGroupIdUserPost(groupId, groupAddUsersBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.addGroupUsersApiAuthserviceGroupGroupIdUserPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async createGroupApiAuthserviceGroupPost(groupCreateBody: GroupCreateBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<GroupCreateResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.createGroupApiAuthserviceGroupPost(groupCreateBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.createGroupApiAuthserviceGroupPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async deleteGroupApiAuthserviceGroupGroupIdDelete(groupId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.deleteGroupApiAuthserviceGroupGroupIdDelete(groupId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.deleteGroupApiAuthserviceGroupGroupIdDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async getGroupApiAuthserviceGroupGroupIdGet(groupId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<GroupDetailResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.getGroupApiAuthserviceGroupGroupIdGet(groupId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.getGroupApiAuthserviceGroupGroupIdGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(groupId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<GroupPermissionsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(groupId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async listGroupUsersApiAuthserviceGroupGroupIdUserGet(groupId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<GroupUserListResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.listGroupUsersApiAuthserviceGroupGroupIdUserGet(groupId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.listGroupUsersApiAuthserviceGroupGroupIdUserGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async listGroupsApiAuthserviceGroupGet(page?: number, pageSize?: number, search?: string | null, tenantId?: string | null, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<GroupListResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.listGroupsApiAuthserviceGroupGet(page, pageSize, search, tenantId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.listGroupsApiAuthserviceGroupGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(groupId: string, groupRemoveUsersBody: GroupRemoveUsersBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(groupId, groupRemoveUsersBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(groupId: string, groupPermissionsBody: GroupPermissionsBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(groupId, groupPermissionsBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(groupId: string, groupMemberRoleBatchBody: GroupMemberRoleBatchBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(groupId, groupMemberRoleBatchBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async updateGroupApiAuthserviceGroupGroupIdPatch(groupId: string, groupUpdateBody: GroupUpdateBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.updateGroupApiAuthserviceGroupGroupIdPatch(groupId, groupUpdateBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['GroupApi.updateGroupApiAuthserviceGroupGroupIdPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * GroupApi - factory interface
 */
export const GroupApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = GroupApiFp(configuration)
    return {
        
        addGroupUsersApiAuthserviceGroupGroupIdUserPost(requestParameters: GroupApiAddGroupUsersApiAuthserviceGroupGroupIdUserPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.addGroupUsersApiAuthserviceGroupGroupIdUserPost(requestParameters.groupId, requestParameters.groupAddUsersBody, options).then((request) => request(axios, basePath));
        },
        
        createGroupApiAuthserviceGroupPost(requestParameters: GroupApiCreateGroupApiAuthserviceGroupPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<GroupCreateResponse> {
            return localVarFp.createGroupApiAuthserviceGroupPost(requestParameters.groupCreateBody, options).then((request) => request(axios, basePath));
        },
        
        deleteGroupApiAuthserviceGroupGroupIdDelete(requestParameters: GroupApiDeleteGroupApiAuthserviceGroupGroupIdDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.deleteGroupApiAuthserviceGroupGroupIdDelete(requestParameters.groupId, options).then((request) => request(axios, basePath));
        },
        
        getGroupApiAuthserviceGroupGroupIdGet(requestParameters: GroupApiGetGroupApiAuthserviceGroupGroupIdGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<GroupDetailResponse> {
            return localVarFp.getGroupApiAuthserviceGroupGroupIdGet(requestParameters.groupId, options).then((request) => request(axios, basePath));
        },
        
        getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(requestParameters: GroupApiGetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<GroupPermissionsResponse> {
            return localVarFp.getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(requestParameters.groupId, options).then((request) => request(axios, basePath));
        },
        
        listGroupUsersApiAuthserviceGroupGroupIdUserGet(requestParameters: GroupApiListGroupUsersApiAuthserviceGroupGroupIdUserGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<GroupUserListResponse> {
            return localVarFp.listGroupUsersApiAuthserviceGroupGroupIdUserGet(requestParameters.groupId, options).then((request) => request(axios, basePath));
        },
        
        listGroupsApiAuthserviceGroupGet(requestParameters: GroupApiListGroupsApiAuthserviceGroupGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<GroupListResponse> {
            return localVarFp.listGroupsApiAuthserviceGroupGet(requestParameters.page, requestParameters.pageSize, requestParameters.search, requestParameters.tenantId, options).then((request) => request(axios, basePath));
        },
        
        removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(requestParameters: GroupApiRemoveGroupUsersApiAuthserviceGroupGroupIdUserRemovePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(requestParameters.groupId, requestParameters.groupRemoveUsersBody, options).then((request) => request(axios, basePath));
        },
        
        setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(requestParameters: GroupApiSetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPutRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(requestParameters.groupId, requestParameters.groupPermissionsBody, options).then((request) => request(axios, basePath));
        },
        
        setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(requestParameters: GroupApiSetMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(requestParameters.groupId, requestParameters.groupMemberRoleBatchBody, options).then((request) => request(axios, basePath));
        },
        
        updateGroupApiAuthserviceGroupGroupIdPatch(requestParameters: GroupApiUpdateGroupApiAuthserviceGroupGroupIdPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.updateGroupApiAuthserviceGroupGroupIdPatch(requestParameters.groupId, requestParameters.groupUpdateBody, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for addGroupUsersApiAuthserviceGroupGroupIdUserPost operation in GroupApi.
 */
export interface GroupApiAddGroupUsersApiAuthserviceGroupGroupIdUserPostRequest {
    readonly groupId: string

    readonly groupAddUsersBody: GroupAddUsersBody
}

/**
 * Request parameters for createGroupApiAuthserviceGroupPost operation in GroupApi.
 */
export interface GroupApiCreateGroupApiAuthserviceGroupPostRequest {
    readonly groupCreateBody: GroupCreateBody
}

/**
 * Request parameters for deleteGroupApiAuthserviceGroupGroupIdDelete operation in GroupApi.
 */
export interface GroupApiDeleteGroupApiAuthserviceGroupGroupIdDeleteRequest {
    readonly groupId: string
}

/**
 * Request parameters for getGroupApiAuthserviceGroupGroupIdGet operation in GroupApi.
 */
export interface GroupApiGetGroupApiAuthserviceGroupGroupIdGetRequest {
    readonly groupId: string
}

/**
 * Request parameters for getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet operation in GroupApi.
 */
export interface GroupApiGetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGetRequest {
    readonly groupId: string
}

/**
 * Request parameters for listGroupUsersApiAuthserviceGroupGroupIdUserGet operation in GroupApi.
 */
export interface GroupApiListGroupUsersApiAuthserviceGroupGroupIdUserGetRequest {
    readonly groupId: string
}

/**
 * Request parameters for listGroupsApiAuthserviceGroupGet operation in GroupApi.
 */
export interface GroupApiListGroupsApiAuthserviceGroupGetRequest {
    readonly page?: number

    readonly pageSize?: number

    readonly search?: string | null

    readonly tenantId?: string | null
}

/**
 * Request parameters for removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost operation in GroupApi.
 */
export interface GroupApiRemoveGroupUsersApiAuthserviceGroupGroupIdUserRemovePostRequest {
    readonly groupId: string

    readonly groupRemoveUsersBody: GroupRemoveUsersBody
}

/**
 * Request parameters for setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut operation in GroupApi.
 */
export interface GroupApiSetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPutRequest {
    readonly groupId: string

    readonly groupPermissionsBody: GroupPermissionsBody
}

/**
 * Request parameters for setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch operation in GroupApi.
 */
export interface GroupApiSetMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatchRequest {
    readonly groupId: string

    readonly groupMemberRoleBatchBody: GroupMemberRoleBatchBody
}

/**
 * Request parameters for updateGroupApiAuthserviceGroupGroupIdPatch operation in GroupApi.
 */
export interface GroupApiUpdateGroupApiAuthserviceGroupGroupIdPatchRequest {
    readonly groupId: string

    readonly groupUpdateBody: GroupUpdateBody
}

/**
 * GroupApi - object-oriented interface
 */
export class GroupApi extends BaseAPI {
    
    public addGroupUsersApiAuthserviceGroupGroupIdUserPost(requestParameters: GroupApiAddGroupUsersApiAuthserviceGroupGroupIdUserPostRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).addGroupUsersApiAuthserviceGroupGroupIdUserPost(requestParameters.groupId, requestParameters.groupAddUsersBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public createGroupApiAuthserviceGroupPost(requestParameters: GroupApiCreateGroupApiAuthserviceGroupPostRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).createGroupApiAuthserviceGroupPost(requestParameters.groupCreateBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public deleteGroupApiAuthserviceGroupGroupIdDelete(requestParameters: GroupApiDeleteGroupApiAuthserviceGroupGroupIdDeleteRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).deleteGroupApiAuthserviceGroupGroupIdDelete(requestParameters.groupId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public getGroupApiAuthserviceGroupGroupIdGet(requestParameters: GroupApiGetGroupApiAuthserviceGroupGroupIdGetRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).getGroupApiAuthserviceGroupGroupIdGet(requestParameters.groupId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(requestParameters: GroupApiGetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGetRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet(requestParameters.groupId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public listGroupUsersApiAuthserviceGroupGroupIdUserGet(requestParameters: GroupApiListGroupUsersApiAuthserviceGroupGroupIdUserGetRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).listGroupUsersApiAuthserviceGroupGroupIdUserGet(requestParameters.groupId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public listGroupsApiAuthserviceGroupGet(requestParameters: GroupApiListGroupsApiAuthserviceGroupGetRequest = {}, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).listGroupsApiAuthserviceGroupGet(requestParameters.page, requestParameters.pageSize, requestParameters.search, requestParameters.tenantId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(requestParameters: GroupApiRemoveGroupUsersApiAuthserviceGroupGroupIdUserRemovePostRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost(requestParameters.groupId, requestParameters.groupRemoveUsersBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(requestParameters: GroupApiSetGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPutRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut(requestParameters.groupId, requestParameters.groupPermissionsBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(requestParameters: GroupApiSetMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatchRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).setMemberRolesBatchApiAuthserviceGroupGroupIdUserRolePatch(requestParameters.groupId, requestParameters.groupMemberRoleBatchBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public updateGroupApiAuthserviceGroupGroupIdPatch(requestParameters: GroupApiUpdateGroupApiAuthserviceGroupGroupIdPatchRequest, options?: RawAxiosRequestConfig) {
        return GroupApiFp(this.configuration).updateGroupApiAuthserviceGroupGroupIdPatch(requestParameters.groupId, requestParameters.groupUpdateBody, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * RoleApi - axios parameter creator
 */
export const RoleApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        
        createRoleApiAuthserviceRolePost: async (roleCreateBody: RoleCreateBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'roleCreateBody' is not null or undefined
            assertParamExists('createRoleApiAuthserviceRolePost', 'roleCreateBody', roleCreateBody)
            const localVarPath = `/api/authservice/role`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(roleCreateBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        deleteRoleApiAuthserviceRoleRoleIdDelete: async (roleId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'roleId' is not null or undefined
            assertParamExists('deleteRoleApiAuthserviceRoleRoleIdDelete', 'roleId', roleId)
            const localVarPath = `/api/authservice/role/{role_id}`
                .replace(`{${"role_id"}}`, encodeURIComponent(String(roleId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'DELETE', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet: async (roleId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'roleId' is not null or undefined
            assertParamExists('getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet', 'roleId', roleId)
            const localVarPath = `/api/authservice/role/{role_id}/permissions`
                .replace(`{${"role_id"}}`, encodeURIComponent(String(roleId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        listPermissionGroupsApiAuthserviceRolePermissionGroupsGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/role/permission-groups`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        listRolesApiAuthserviceRoleGet: async (options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/role`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut: async (roleId: string, rolePermissionsBody: RolePermissionsBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'roleId' is not null or undefined
            assertParamExists('setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut', 'roleId', roleId)
            // verify required parameter 'rolePermissionsBody' is not null or undefined
            assertParamExists('setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut', 'rolePermissionsBody', rolePermissionsBody)
            const localVarPath = `/api/authservice/role/{role_id}/permissions`
                .replace(`{${"role_id"}}`, encodeURIComponent(String(roleId)));
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PUT', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(rolePermissionsBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * RoleApi - functional programming interface
 */
export const RoleApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = RoleApiAxiosParamCreator(configuration)
    return {
        
        async createRoleApiAuthserviceRolePost(roleCreateBody: RoleCreateBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<RoleCreateResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.createRoleApiAuthserviceRolePost(roleCreateBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.createRoleApiAuthserviceRolePost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async deleteRoleApiAuthserviceRoleRoleIdDelete(roleId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.deleteRoleApiAuthserviceRoleRoleIdDelete(roleId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.deleteRoleApiAuthserviceRoleRoleIdDelete']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(roleId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<RolePermissionsResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(roleId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Array<PermissionGroupItem>>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.listPermissionGroupsApiAuthserviceRolePermissionGroupsGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async listRolesApiAuthserviceRoleGet(options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<Array<RoleItem>>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.listRolesApiAuthserviceRoleGet(options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.listRolesApiAuthserviceRoleGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(roleId: string, rolePermissionsBody: RolePermissionsBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(roleId, rolePermissionsBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['RoleApi.setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * RoleApi - factory interface
 */
export const RoleApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = RoleApiFp(configuration)
    return {
        
        createRoleApiAuthserviceRolePost(requestParameters: RoleApiCreateRoleApiAuthserviceRolePostRequest, options?: RawAxiosRequestConfig): AxiosPromise<RoleCreateResponse> {
            return localVarFp.createRoleApiAuthserviceRolePost(requestParameters.roleCreateBody, options).then((request) => request(axios, basePath));
        },
        
        deleteRoleApiAuthserviceRoleRoleIdDelete(requestParameters: RoleApiDeleteRoleApiAuthserviceRoleRoleIdDeleteRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.deleteRoleApiAuthserviceRoleRoleIdDelete(requestParameters.roleId, options).then((request) => request(axios, basePath));
        },
        
        getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(requestParameters: RoleApiGetRolePermissionsApiAuthserviceRoleRoleIdPermissionsGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<RolePermissionsResponse> {
            return localVarFp.getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(requestParameters.roleId, options).then((request) => request(axios, basePath));
        },
        
        listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options?: RawAxiosRequestConfig): AxiosPromise<Array<PermissionGroupItem>> {
            return localVarFp.listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options).then((request) => request(axios, basePath));
        },
        
        listRolesApiAuthserviceRoleGet(options?: RawAxiosRequestConfig): AxiosPromise<Array<RoleItem>> {
            return localVarFp.listRolesApiAuthserviceRoleGet(options).then((request) => request(axios, basePath));
        },
        
        setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(requestParameters: RoleApiSetRolePermissionsApiAuthserviceRoleRoleIdPermissionsPutRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(requestParameters.roleId, requestParameters.rolePermissionsBody, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for createRoleApiAuthserviceRolePost operation in RoleApi.
 */
export interface RoleApiCreateRoleApiAuthserviceRolePostRequest {
    readonly roleCreateBody: RoleCreateBody
}

/**
 * Request parameters for deleteRoleApiAuthserviceRoleRoleIdDelete operation in RoleApi.
 */
export interface RoleApiDeleteRoleApiAuthserviceRoleRoleIdDeleteRequest {
    readonly roleId: string
}

/**
 * Request parameters for getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet operation in RoleApi.
 */
export interface RoleApiGetRolePermissionsApiAuthserviceRoleRoleIdPermissionsGetRequest {
    readonly roleId: string
}

/**
 * Request parameters for setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut operation in RoleApi.
 */
export interface RoleApiSetRolePermissionsApiAuthserviceRoleRoleIdPermissionsPutRequest {
    readonly roleId: string

    readonly rolePermissionsBody: RolePermissionsBody
}

/**
 * RoleApi - object-oriented interface
 */
export class RoleApi extends BaseAPI {
    
    public createRoleApiAuthserviceRolePost(requestParameters: RoleApiCreateRoleApiAuthserviceRolePostRequest, options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).createRoleApiAuthserviceRolePost(requestParameters.roleCreateBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public deleteRoleApiAuthserviceRoleRoleIdDelete(requestParameters: RoleApiDeleteRoleApiAuthserviceRoleRoleIdDeleteRequest, options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).deleteRoleApiAuthserviceRoleRoleIdDelete(requestParameters.roleId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(requestParameters: RoleApiGetRolePermissionsApiAuthserviceRoleRoleIdPermissionsGetRequest, options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).getRolePermissionsApiAuthserviceRoleRoleIdPermissionsGet(requestParameters.roleId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public listRolesApiAuthserviceRoleGet(options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).listRolesApiAuthserviceRoleGet(options).then((request) => request(this.axios, this.basePath));
    }

    
    public setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(requestParameters: RoleApiSetRolePermissionsApiAuthserviceRoleRoleIdPermissionsPutRequest, options?: RawAxiosRequestConfig) {
        return RoleApiFp(this.configuration).setRolePermissionsApiAuthserviceRoleRoleIdPermissionsPut(requestParameters.roleId, requestParameters.rolePermissionsBody, options).then((request) => request(this.axios, this.basePath));
    }
}



/**
 * UserApi - axios parameter creator
 */
export const UserApiAxiosParamCreator = function (configuration?: Configuration) {
    return {
        /**
         * System-admin creates a user. Default role is user; can assign any role for high-privilege users.
         * @summary Create User
         * @param {CreateUserBody} createUserBody 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        createUserApiAuthserviceUserPost: async (createUserBody: CreateUserBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'createUserBody' is not null or undefined
            assertParamExists('createUserApiAuthserviceUserPost', 'createUserBody', createUserBody)
            const localVarPath = `/api/authservice/user`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'POST', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(createUserBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        getUserApiAuthserviceUserUserIdGet: async (userId: string, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('getUserApiAuthserviceUserUserIdGet', 'userId', userId)
            const localVarPath = `/api/authservice/user/{user_id}`
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

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        listUsersApiAuthserviceUserGet: async (page?: number, pageSize?: number, search?: string | null, tenantId?: string | null, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            const localVarPath = `/api/authservice/user`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'GET', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            if (page !== undefined) {
                localVarQueryParameter['page'] = page;
            }

            if (pageSize !== undefined) {
                localVarQueryParameter['page_size'] = pageSize;
            }

            if (search !== undefined) {
                localVarQueryParameter['search'] = search;
            }

            if (tenantId !== undefined) {
                localVarQueryParameter['tenant_id'] = tenantId;
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
        
        resetPasswordApiAuthserviceUserUserIdResetPasswordPatch: async (userId: string, resetPasswordBody: ResetPasswordBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('resetPasswordApiAuthserviceUserUserIdResetPasswordPatch', 'userId', userId)
            // verify required parameter 'resetPasswordBody' is not null or undefined
            assertParamExists('resetPasswordApiAuthserviceUserUserIdResetPasswordPatch', 'resetPasswordBody', resetPasswordBody)
            const localVarPath = `/api/authservice/user/{user_id}/reset_password`
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

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(resetPasswordBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        setUserRoleApiAuthserviceUserUserIdPatch: async (userId: string, userRoleBody: UserRoleBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'userId' is not null or undefined
            assertParamExists('setUserRoleApiAuthserviceUserUserIdPatch', 'userId', userId)
            // verify required parameter 'userRoleBody' is not null or undefined
            assertParamExists('setUserRoleApiAuthserviceUserUserIdPatch', 'userRoleBody', userRoleBody)
            const localVarPath = `/api/authservice/user/{user_id}`
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

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(userRoleBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
        
        setUserRolesBatchApiAuthserviceUserRolePatch: async (userRoleBatchBody: UserRoleBatchBody, options: RawAxiosRequestConfig = {}): Promise<RequestArgs> => {
            // verify required parameter 'userRoleBatchBody' is not null or undefined
            assertParamExists('setUserRolesBatchApiAuthserviceUserRolePatch', 'userRoleBatchBody', userRoleBatchBody)
            const localVarPath = `/api/authservice/user/role`;
            // use dummy base URL string because the URL constructor only accepts absolute URLs.
            const localVarUrlObj = new URL(localVarPath, DUMMY_BASE_URL);
            let baseOptions;
            if (configuration) {
                baseOptions = configuration.baseOptions;
            }

            const localVarRequestOptions = { method: 'PATCH', ...baseOptions, ...options};
            const localVarHeaderParameter = {} as any;
            const localVarQueryParameter = {} as any;

            // authentication HTTPBearer required
            // http bearer authentication required
            await setBearerAuthToObject(localVarHeaderParameter, configuration)

            localVarHeaderParameter['Content-Type'] = 'application/json';
            localVarHeaderParameter['Accept'] = 'application/json';

            setSearchParams(localVarUrlObj, localVarQueryParameter);
            let headersFromBaseOptions = baseOptions && baseOptions.headers ? baseOptions.headers : {};
            localVarRequestOptions.headers = {...localVarHeaderParameter, ...headersFromBaseOptions, ...options.headers};
            localVarRequestOptions.data = serializeDataIfNeeded(userRoleBatchBody, localVarRequestOptions, configuration)

            return {
                url: toPathString(localVarUrlObj),
                options: localVarRequestOptions,
            };
        },
    }
};

/**
 * UserApi - functional programming interface
 */
export const UserApiFp = function(configuration?: Configuration) {
    const localVarAxiosParamCreator = UserApiAxiosParamCreator(configuration)
    return {
        /**
         * System-admin creates a user. Default role is user; can assign any role for high-privilege users.
         * @summary Create User
         * @param {CreateUserBody} createUserBody 
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        async createUserApiAuthserviceUserPost(createUserBody: CreateUserBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<CreateUserResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.createUserApiAuthserviceUserPost(createUserBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.createUserApiAuthserviceUserPost']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async getUserApiAuthserviceUserUserIdGet(userId: string, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UserDetailResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.getUserApiAuthserviceUserUserIdGet(userId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.getUserApiAuthserviceUserUserIdGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async listUsersApiAuthserviceUserGet(page?: number, pageSize?: number, search?: string | null, tenantId?: string | null, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<UserListResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.listUsersApiAuthserviceUserGet(page, pageSize, search, tenantId, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.listUsersApiAuthserviceUserGet']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(userId: string, resetPasswordBody: ResetPasswordBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(userId, resetPasswordBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.resetPasswordApiAuthserviceUserUserIdResetPasswordPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async setUserRoleApiAuthserviceUserUserIdPatch(userId: string, userRoleBody: UserRoleBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.setUserRoleApiAuthserviceUserUserIdPatch(userId, userRoleBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.setUserRoleApiAuthserviceUserUserIdPatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
        
        async setUserRolesBatchApiAuthserviceUserRolePatch(userRoleBatchBody: UserRoleBatchBody, options?: RawAxiosRequestConfig): Promise<(axios?: AxiosInstance, basePath?: string) => AxiosPromise<OkResponse>> {
            const localVarAxiosArgs = await localVarAxiosParamCreator.setUserRolesBatchApiAuthserviceUserRolePatch(userRoleBatchBody, options);
            const localVarOperationServerIndex = configuration?.serverIndex ?? 0;
            const localVarOperationServerBasePath = operationServerMap['UserApi.setUserRolesBatchApiAuthserviceUserRolePatch']?.[localVarOperationServerIndex]?.url;
            return (axios, basePath) => createRequestFunction(localVarAxiosArgs, globalAxios, BASE_PATH, configuration)(axios, localVarOperationServerBasePath || basePath);
        },
    }
};

/**
 * UserApi - factory interface
 */
export const UserApiFactory = function (configuration?: Configuration, basePath?: string, axios?: AxiosInstance) {
    const localVarFp = UserApiFp(configuration)
    return {
        /**
         * System-admin creates a user. Default role is user; can assign any role for high-privilege users.
         * @summary Create User
         * @param {UserApiCreateUserApiAuthserviceUserPostRequest} requestParameters Request parameters.
         * @param {*} [options] Override http request option.
         * @throws {RequiredError}
         */
        createUserApiAuthserviceUserPost(requestParameters: UserApiCreateUserApiAuthserviceUserPostRequest, options?: RawAxiosRequestConfig): AxiosPromise<CreateUserResponse> {
            return localVarFp.createUserApiAuthserviceUserPost(requestParameters.createUserBody, options).then((request) => request(axios, basePath));
        },
        
        getUserApiAuthserviceUserUserIdGet(requestParameters: UserApiGetUserApiAuthserviceUserUserIdGetRequest, options?: RawAxiosRequestConfig): AxiosPromise<UserDetailResponse> {
            return localVarFp.getUserApiAuthserviceUserUserIdGet(requestParameters.userId, options).then((request) => request(axios, basePath));
        },
        
        listUsersApiAuthserviceUserGet(requestParameters: UserApiListUsersApiAuthserviceUserGetRequest = {}, options?: RawAxiosRequestConfig): AxiosPromise<UserListResponse> {
            return localVarFp.listUsersApiAuthserviceUserGet(requestParameters.page, requestParameters.pageSize, requestParameters.search, requestParameters.tenantId, options).then((request) => request(axios, basePath));
        },
        
        resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(requestParameters: UserApiResetPasswordApiAuthserviceUserUserIdResetPasswordPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(requestParameters.userId, requestParameters.resetPasswordBody, options).then((request) => request(axios, basePath));
        },
        
        setUserRoleApiAuthserviceUserUserIdPatch(requestParameters: UserApiSetUserRoleApiAuthserviceUserUserIdPatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.setUserRoleApiAuthserviceUserUserIdPatch(requestParameters.userId, requestParameters.userRoleBody, options).then((request) => request(axios, basePath));
        },
        
        setUserRolesBatchApiAuthserviceUserRolePatch(requestParameters: UserApiSetUserRolesBatchApiAuthserviceUserRolePatchRequest, options?: RawAxiosRequestConfig): AxiosPromise<OkResponse> {
            return localVarFp.setUserRolesBatchApiAuthserviceUserRolePatch(requestParameters.userRoleBatchBody, options).then((request) => request(axios, basePath));
        },
    };
};

/**
 * Request parameters for createUserApiAuthserviceUserPost operation in UserApi.
 */
export interface UserApiCreateUserApiAuthserviceUserPostRequest {
    readonly createUserBody: CreateUserBody
}

/**
 * Request parameters for getUserApiAuthserviceUserUserIdGet operation in UserApi.
 */
export interface UserApiGetUserApiAuthserviceUserUserIdGetRequest {
    readonly userId: string
}

/**
 * Request parameters for listUsersApiAuthserviceUserGet operation in UserApi.
 */
export interface UserApiListUsersApiAuthserviceUserGetRequest {
    readonly page?: number

    readonly pageSize?: number

    readonly search?: string | null

    readonly tenantId?: string | null
}

/**
 * Request parameters for resetPasswordApiAuthserviceUserUserIdResetPasswordPatch operation in UserApi.
 */
export interface UserApiResetPasswordApiAuthserviceUserUserIdResetPasswordPatchRequest {
    readonly userId: string

    readonly resetPasswordBody: ResetPasswordBody
}

/**
 * Request parameters for setUserRoleApiAuthserviceUserUserIdPatch operation in UserApi.
 */
export interface UserApiSetUserRoleApiAuthserviceUserUserIdPatchRequest {
    readonly userId: string

    readonly userRoleBody: UserRoleBody
}

/**
 * Request parameters for setUserRolesBatchApiAuthserviceUserRolePatch operation in UserApi.
 */
export interface UserApiSetUserRolesBatchApiAuthserviceUserRolePatchRequest {
    readonly userRoleBatchBody: UserRoleBatchBody
}

/**
 * UserApi - object-oriented interface
 */
export class UserApi extends BaseAPI {
    /**
     * System-admin creates a user. Default role is user; can assign any role for high-privilege users.
     * @summary Create User
     * @param {UserApiCreateUserApiAuthserviceUserPostRequest} requestParameters Request parameters.
     * @param {*} [options] Override http request option.
     * @throws {RequiredError}
     */
    public createUserApiAuthserviceUserPost(requestParameters: UserApiCreateUserApiAuthserviceUserPostRequest, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).createUserApiAuthserviceUserPost(requestParameters.createUserBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public getUserApiAuthserviceUserUserIdGet(requestParameters: UserApiGetUserApiAuthserviceUserUserIdGetRequest, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).getUserApiAuthserviceUserUserIdGet(requestParameters.userId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public listUsersApiAuthserviceUserGet(requestParameters: UserApiListUsersApiAuthserviceUserGetRequest = {}, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).listUsersApiAuthserviceUserGet(requestParameters.page, requestParameters.pageSize, requestParameters.search, requestParameters.tenantId, options).then((request) => request(this.axios, this.basePath));
    }

    
    public resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(requestParameters: UserApiResetPasswordApiAuthserviceUserUserIdResetPasswordPatchRequest, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).resetPasswordApiAuthserviceUserUserIdResetPasswordPatch(requestParameters.userId, requestParameters.resetPasswordBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public setUserRoleApiAuthserviceUserUserIdPatch(requestParameters: UserApiSetUserRoleApiAuthserviceUserUserIdPatchRequest, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).setUserRoleApiAuthserviceUserUserIdPatch(requestParameters.userId, requestParameters.userRoleBody, options).then((request) => request(this.axios, this.basePath));
    }

    
    public setUserRolesBatchApiAuthserviceUserRolePatch(requestParameters: UserApiSetUserRolesBatchApiAuthserviceUserRolePatchRequest, options?: RawAxiosRequestConfig) {
        return UserApiFp(this.configuration).setUserRolesBatchApiAuthserviceUserRolePatch(requestParameters.userRoleBatchBody, options).then((request) => request(this.axios, this.basePath));
    }
}



