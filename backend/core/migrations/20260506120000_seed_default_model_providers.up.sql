-- +migrate Up

-- Seed default_model_providers from lazy模型汇总表_副本.xlsx (name, description, base_url).
-- id: 32-char hex, same format as backend/core/common.GenerateID() (UUID v4).

INSERT INTO "default_model_providers" ("id", "name", "description", "base_url", "created_at", "updated_at", "deleted_at") VALUES
  ('c4c41f0440c64c1dae6a41e7cf3d445b', 'Claude', $d0$Anthropic 打造的顶尖 AI 基座，具备强大的自适应思考能力与原生视觉支持，在代码开发与复杂 Agent 任务上业界领先。

获取 API Key：
https://console.anthropic.com/settings/keys

申请教程：

1. 访问 Anthropic Console，使用海外邮箱或 Google 账号直接注册。

2. 登录后（需验证海外手机号并绑定外币信用卡结算），进入左侧菜单的 Settings → API Keys 页面。

3. 点击 Create Key，输入辨识名称后即可生成，请务必当场复制并妥善保存（关闭弹窗后无法再次查看完整 Key）。$d0$, 'https://api.anthropic.com/v1', now(), now(), NULL),
  ('eadef5c69d2a4496809861634fe340b7', 'DeepSeek', $d1$国产顶尖大模型，推理模型性价比极高，支持深度推理与长链思考输出。

获取 API Key：
https://platform.deepseek.com/api_keys

申请教程：

1. 访问 DeepSeek 开放平台，使用手机号或邮箱完成注册。

2. 登录后进入左侧导航栏的 API Keys 页面，点击"创建 API Key"。

3. 为 Key 命名后点击创建，系统会生成一串密钥，请复制并妥善保存至你的代码配置中。$d1$, 'https://api.deepseek.com', now(), now(), NULL),
  ('3d6fe37fbe514ca7b2aedec309a6abd4', 'Doubao', $d2$字节跳动火山引擎出品，旗舰模型深度思考能力极强，全面覆盖复杂推理、代码开发及高精度文生图等多模态场景。

获取 API Key：
https://console.volcengine.com/iam/keymanage/

申请教程：

1. 访问火山引擎（Volcengine）控制台，使用手机号或邮箱注册火山引擎账号并完成实名认证。

2. 登录后，在控制台右上角点击账号头像，进入"API 访问密钥"管理页面。

3. 点击"新建密钥"，系统会自动生成 Access Key ID 和 Secret Access Key，请妥善保管。$d2$, 'https://ark.cn-beijing.volces.com/api/v3', now(), now(), NULL),
  ('8b2d73f125c44725882d08e348185acc', 'GLM', $d3$清华出身的国产大模型，Coding 能力已对齐顶尖闭源模型，深度适配 Agent 工作流、工具调用与超长上下文解析。

获取 API Key：
https://open.bigmodel.cn/usercenter/apikeys

申请教程：

1. 访问智谱 AI 开放平台，使用手机号或微信扫码注册并实名。

2. 登录后进入右上角的"控制台"，在左侧菜单选择"API Keys"。

3. 点击"添加新的 API Key"，设置便于区分的名称，生成后复制完整的 Key 即可使用。$d3$, 'https://open.bigmodel.cn/api/paas/v4', now(), now(), NULL),
  ('2714c5f4af594f23a1fddac3153bbb95', 'Kimi', $d4$Moonshot AI 出品，支持超长上下文推理，Agentic Coding 与长周期执行能力出众，中英文处理极佳。

获取 API Key：
https://platform.moonshot.cn/console/api-keys

申请教程：

1. 访问 Kimi 开放平台（Moonshot 开发者中心），使用手机号验证注册。

2. 登录后在左侧导航栏选择"API Key 管理"页面。

3. 点击"新建 API Key"，输入名称后点击生成，请当场复制这段密钥并安全保存。$d4$, 'https://api.moonshot.cn/', now(), now(), NULL),
  ('d647ba631e6c439bbfb968ff84b1aac5', 'Minimax', $d5$MiniMax 自研的通用大模型，开启模型自我迭代，在文本对话、超拟人语音合成及视频生成领域稳居第一梯队。

获取 API Key：
https://platform.minimaxi.com/

申请教程：

1. 访问 MiniMax 开放平台主页，点击右上角登录/注册开发者账号。

2. 登录后进入后台工作台，在左侧导航栏找到 "账户管理"，点击展开后选择 "接口密钥"（或者"订阅管理"下的 Token Plan）。

3. 点击"创建新的 API Key"，设置名称并确认后，复制生成的 API Key 用于接口调用（请注意按量付费 Key 和 Token Plan Key 不互通）。$d5$, 'https://api.minimaxi.com/v1', now(), now(), NULL),
  ('e93bdc713dd14f16a9a6a9b282ad7d1d', 'OpenAI', $d6$AI 行业绝对标杆，引领智能前沿，在复杂编码、专业工作流与子代理生态上最为完善。

获取 API Key：
https://platform.openai.com/api-keys

申请教程：

1. 访问 OpenAI Platform，使用邮箱或 Google 账号注册（需具备海外网络环境及海外手机号验证）。

2. 在左侧 Dashboard 菜单中选择"API keys"选项卡（需先在 Billing 中绑定海外信用卡并充值）。

3. 点击"Create new secret key"，为 Key 命名并配置权限，点击生成后立刻复制（该密钥仅显示一次）。$d6$, 'https://api.openai.com/v1', now(), now(), NULL),
  ('7ad36d2989c14f158a8c5f346d1054a8', 'Qwen', $d7$阿里云开源与闭源双轨并行的王牌模型，全家桶覆盖文本、视觉、语音及图像编辑，国内生态最为丰富，API 调用极其便捷。

获取 API Key：
https://bailian.console.aliyun.com/?apiKey=1#/api-key

申请教程：

1. 访问阿里云百炼控制台，使用阿里云账号（支持支付宝/钉钉扫码）登录并开通百炼服务。

2. 在控制台右上角点击头像，进入"API-KEY"管理页面。

3. 点击"创建 API-KEY"，系统会立即生成一串鉴权密钥，点击复制即可在应用中使用。$d7$, 'https://dashscope.aliyuncs.com/api/v1', now(), now(), NULL),
  ('72ebcc11418d432887c28145b1600722', 'SenseNova', $d8$商汤科技打造的国产重磅基座，深度推理与多模态理解能力出色，综合性能强悍。

获取 API Key：
https://console.sensecore.cn/cn-sh-01/aistudio/management/api-key

申请教程：

1. 访问商汤大模型开放平台（SenseCore大装置），注册并完成企业或个人开发者认证。

2. 登录控制台，在左侧导航栏找到"API-Key管理"。

3. 点击"创建API-Key"，自定义名称后即可生成，复制该 API Key 即可进行模型调用。$d8$, 'https://api.sensenova.cn', now(), now(), NULL),
  ('f756580d5758487ea88691268169308c', 'SiliconFlow', $d9$极致高效的模型 API 聚合加速平台，提供一站式、高并发调用服务，价格极其优惠。

获取 API Key：
https://cloud.siliconflow.cn/account/ak

申请教程：

1. 访问 SiliconFlow 云平台，使用手机号、微信或邮箱注册账号。

2. 登录控制台，在左侧菜单栏中点击"API 密钥"选项。

3. 点击"新建 API 密钥"，输入自定义名称描述，生成后一键复制，即可轻松接入各大开源旗舰模型。$d9$, 'https://api.siliconflow.cn/v1', now(), now(), NULL);
