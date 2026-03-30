

您的项目已经成功配置了 OpenAPI 接口自动生成功能。


```bash
npm run dev
```
**说明**：项目启动时会自动生成 Auth 服务的 TypeScript 接口代码


```typescript
// 导入生成的 API 类
import { AuthApi, Configuration } from '@/api/generated/auth-client';

// 配置 API 基础信息
const config = new Configuration({
  basePath: 'http://localhost:8000',
});

const authApi = new AuthApi(config);

// 调用登录接口
async function login() {
  const response = await authApi.loginApiAuthLoginPost({
    loginBody: {
      username: 'myusername',
      password: 'mypassword',
    },
  });
  
  const { access_token, refresh_token } = response.data;
  console.log('登录成功！Token:', access_token);
}
```


```bash
npm run dev

npm run gen:auth

npm run gen:openapi
```


| 类型 | 路径 | 说明 |
|------|------|------|
| OpenAPI 规范 | `scripts/openapi/specs/auth-openapi.yaml` | Auth 服务的 API 定义 |
| 生成的接口 | `src/api/generated/auth-client/` | TypeScript 接口代码 |
| 使用示例 | `src/api/auth-example.ts` | 完整的使用示例代码 |
| 详细文档 | `scripts/openapi/README.md` | 完整配置和使用文档 |


根据您的 OpenAPI 规范，已生成以下 API 类：

- ✅ **AuthApi** - 认证相关接口（登录、注册、登出等）
- ✅ **UserApi** - 用户管理接口
- ✅ **RoleApi** - 角色管理接口
- ✅ **GroupApi** - 用户组管理接口
- ✅ **AuthorizationApi** - 授权相关接口


参考 `src/api/auth-example.ts` 文件，其中包含：

- ✅ 用户注册
- ✅ 用户登录
- ✅ 获取当前用户信息
- ✅ 刷新 Token
- ✅ 修改密码
- ✅ 登出
- ✅ 用户列表
- ✅ 创建用户
- ✅ 角色列表


1. **开始使用接口**
   - 复制 `src/api/auth-example.ts` 中的代码
   - 根据您的需求修改和调用

2. **更新接口**
   - 当后端 API 变更时，更新 `scripts/openapi/specs/auth-openapi.yaml`
   - 运行 `npm run gen:auth` 重新生成

3. **添加新服务**
   - 在 `scripts/openapi/specs/` 添加新的 YAML 文件
   - 修改 `scripts/openapi/generate-api.mjs` 配置
   - 运行生成命令


**Q: 修改生成的代码会怎样？**  
A: 不要修改生成的代码，因为下次生成时会被覆盖。如需自定义，创建包装类。

**Q: 如何更新接口？**  
A: 更新 YAML 文件后运行 `npm run gen:auth` 即可。

**Q: 启动很慢？**  
A: 首次启动需要生成接口，后续会使用缓存，速度会快很多。

---

🎉 **配置完成！现在您可以开始使用类型安全的 API 接口了。**

查看详细文档：[scripts/openapi/README.md](./scripts/openapi/README.md)
