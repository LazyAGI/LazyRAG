

✅ 已成功配置 OpenAPI 接口自动生成功能

- 位置：`scripts/openapi/specs/auth-openapi.yaml`
- 内容：LazyRAG 认证与授权服务的完整 API 定义

- 位置：`src/api/generated/auth-client/`
- 包含文件：
  - `api.ts` - API 类定义和接口
  - `configuration.ts` - 配置类
  - `base.ts` - 基础类
  - `common.ts` - 通用工具
  - `index.ts` - 导出入口

- **启动时自动生成**：运行 `npm run dev` 时会自动执行接口生成
- **手动生成命令**：
  ```bash
  npm run gen:auth        # 生成 auth 接口
  npm run gen:openapi     # 生成所有接口
  ```

- `scripts/openapi/generate-api.mjs` - 主生成脚本
- `scripts/openapi/generate-auth.sh` - Auth 接口生成脚本（已添加 Java 环境配置）
- `scripts/openapi/openapi-generator-config.json` - OpenAPI Generator 配置
- `scripts/openapi/README.md` - 详细使用文档

- `src/api/auth-example.ts` - 包含所有主要 API 的使用示例


✅ **Java 17** - 已通过 Homebrew 安装
- 路径：`/opt/homebrew/opt/openjdk@17/bin/java`
- 版本：OpenJDK 17.0.18


```bash
npm run dev
```
启动开发服务器前会自动生成最新的 API 接口

```bash
npm run gen:auth

npm run gen:openapi

npm run gen:openapi auth
```


```typescript
import { AuthApi, Configuration } from '@/api/generated/auth-client';

// 创建配置
const config = new Configuration({
  basePath: 'http://localhost:8000',
  accessToken: 'your-token-here',
});

// 创建 API 实例
const authApi = new AuthApi(config);

// 调用接口
const response = await authApi.loginApiAuthLoginPost({
  loginBody: {
    username: 'user',
    password: 'pass',
  },
});
```


生成脚本会计算 OpenAPI 文件的 SHA256 哈希值，只有当文件内容变化时才会重新生成接口，避免不必要的重复生成。

缓存文件：`scripts/openapi/.openapi-cache.json`


1. **更新 OpenAPI 规范**
   - 当后端 API 有变更时，更新 `scripts/openapi/specs/auth-openapi.yaml`
   - 重新运行 `npm run gen:auth` 生成新接口

2. **添加其他服务的接口**
   - 在 `scripts/openapi/specs/` 目录添加新的 OpenAPI YAML 文件
   - 修改 `scripts/openapi/generate-api.mjs` 添加新的 API 配置
   - 运行生成命令

3. **集成到项目中**
   - 使用生成的 API 类替换现有的手动编写的接口调用
   - 参考 `src/api/auth-example.ts` 中的示例代码


- [OpenAPI Generator 文档](https://openapi-generator.tech/)
- [项目 OpenAPI 配置说明](./scripts/openapi/README.md)
- [API 使用示例](./src/api/auth-example.ts)


1. 生成的代码不要手动修改，因为下次生成时会被覆盖
2. 如需自定义功能，可以创建包装类或扩展类
3. 确保 Java 环境变量正确配置（已在生成脚本中处理）
4. 首次运行需要下载 OpenAPI Generator，可能需要较长时间

---

配置完成日期：2026-03-11
