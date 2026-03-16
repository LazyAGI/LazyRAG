/**
 * Auth API 使用示例
 * 
 * 本文件展示如何使用自动生成的 Auth API 客户端
 */

import { AuthApi, UserApi, RoleApi, Configuration } from '@/api/generated/auth-client';

// 1. 创建 API 配置
const config = new Configuration({
  basePath: 'http://localhost:8000', // API 基础路径
  // 如果需要认证，可以添加 accessToken
  // accessToken: 'your-token-here',
});

// 2. 创建 API 实例
const authApi = new AuthApi(config);

// 3. 使用示例

/**
 * 用户注册
 */
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

/**
 * 用户登录
 */
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

/**
 * 获取当前用户信息
 */
export async function getCurrentUser(token: string) {
  try {
    // 创建带 token 的配置
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

/**
 * 刷新 Token
 */
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

/**
 * 修改密码
 */
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

/**
 * 登出
 */
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

/**
 * 获取用户列表
 */
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

/**
 * 创建用户
 */
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

/**
 * 获取角色列表
 */
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

// 在实际项目中的使用示例：
/*
// 在 React 组件中使用
import { loginUser, getCurrentUser } from '@/api/auth-example';

function LoginComponent() {
  const handleLogin = async () => {
    try {
      const loginResponse = await loginUser('username', 'password');
      const { access_token } = loginResponse;
      
      // 保存 token
      localStorage.setItem('access_token', access_token);
      
      // 获取用户信息
      const userInfo = await getCurrentUser(access_token);
      console.log('当前用户:', userInfo);
    } catch (error) {
      console.error('登录流程失败:', error);
    }
  };
  
  return <button onClick={handleLogin}>登录</button>;
}
*/
