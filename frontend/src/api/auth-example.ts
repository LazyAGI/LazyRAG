

import { AuthApi, UserApi, RoleApi, Configuration } from '@/api/generated/auth-client';

const config = new Configuration({
  basePath: 'http://localhost:8000',
  // accessToken: 'your-token-here',
});

const authApi = new AuthApi(config);



export async function registerUser(username: string, password: string, email?: string) {
  try {
    const response = await authApi.registerApiAuthserviceAuthRegisterPost({
      registerBody: {
        username,
        password,
        confirm_password: password,
        email,
      },
    });
    return response.data;
  } catch (error) {
    console.error('注册失败:', error);
    throw error;
  }
}


export async function loginUser(username: string, password: string) {
  try {
    const response = await authApi.loginApiAuthserviceAuthLoginPost({
      loginBody: {
        username,
        password,
      },
    });
    return response.data;
  } catch (error) {
    console.error('登录失败:', error);
    throw error;
  }
}


export async function getCurrentUser(token: string) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedAuthApi = new AuthApi(authConfig);
    
    const response = await authenticatedAuthApi.meApiAuthserviceAuthMeGet();
    return response.data;
  } catch (error) {
    console.error('获取用户信息失败:', error);
    throw error;
  }
}


export async function refreshToken(refreshToken: string) {
  try {
    const response = await authApi.refreshApiAuthserviceAuthRefreshPost({
      refreshBody: {
        refresh_token: refreshToken,
      },
    });
    return response.data;
  } catch (error) {
    console.error('刷新 Token 失败:', error);
    throw error;
  }
}


export async function changePassword(token: string, oldPassword: string, newPassword: string) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedAuthApi = new AuthApi(authConfig);
    
    const response = await authenticatedAuthApi.changePasswordApiAuthserviceAuthChangePasswordPost({
      changePasswordBody: {
        old_password: oldPassword,
        new_password: newPassword,
      },
    });
    return response.data;
  } catch (error) {
    console.error('修改密码失败:', error);
    throw error;
  }
}


export async function logoutUser(token: string, refreshToken?: string) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedAuthApi = new AuthApi(authConfig);
    
    const response = await authenticatedAuthApi.logoutApiAuthserviceAuthLogoutPost({
      logoutBody: {
        refresh_token: refreshToken,
      },
    });
    return response.data;
  } catch (error) {
    console.error('登出失败:', error);
    throw error;
  }
}


export async function getUserList(token: string, page = 1, pageSize = 20, search?: string) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedUserApi = new UserApi(authConfig);
    
    const response = await authenticatedUserApi.listUsersApiAuthserviceUserGet({
      page,
      pageSize,
      search,
    });
    return response.data;
  } catch (error) {
    console.error('获取用户列表失败:', error);
    throw error;
  }
}


export async function createUser(
  token: string,
  username: string,
  password: string,
  email?: string,
  roleId?: string
) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedUserApi = new UserApi(authConfig);
    
    const response = await authenticatedUserApi.createUserApiAuthserviceUserPost({
      createUserBody: {
        username,
        password,
        email,
        role_id: roleId,
      },
    });
    return response.data;
  } catch (error) {
    console.error('创建用户失败:', error);
    throw error;
  }
}


export async function getRoleList(token: string) {
  try {
    const authConfig = new Configuration({
      basePath: 'http://localhost:8000',
      accessToken: token,
    });
    const authenticatedRoleApi = new RoleApi(authConfig);
    
    const response = await authenticatedRoleApi.listRolesApiAuthserviceRoleGet();
    return response.data;
  } catch (error) {
    console.error('获取角色列表失败:', error);
    throw error;
  }
}


