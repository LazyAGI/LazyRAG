import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Form, Input, Modal, Popconfirm, Select, Tag, Tooltip, message } from "antd";
import {
  CheckCircleFilled,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  KeyOutlined,
  PlusCircleOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  UpOutlined,
} from "@ant-design/icons";
import { AgentAppsAuth } from "@/components/auth";
import { BASE_URL, axiosInstance, getLocalizedErrorMessage } from "@/components/request";
import type { RawAxiosRequestConfig } from "axios";
import "./index.scss";

type ModelCapability =
  | "LLM_CHAT"
  | "EMBEDDING"
  | "VLM"
  | "RERANK"
  | "ASR"
  | "TTS"
  | "TEXT_TO_IMAGE"
  | "MULTIMODAL_EMBEDDING"
  | "IMAGE_EDITING"
  | "LLM_SELF_EVOLUTION";

interface ProviderModel {
  id: string;
  name: string;
  capability: ModelCapability;
  builtIn: boolean;
  enabled: boolean;
}

interface ProviderOption {
  id: string;
  name: string;
  brand: string;
  logoUrl?: string;
  headline: string;
  source: string;
  baseUrl: string;
  capabilities: ModelCapability[];
  models: ProviderModel[];
}

interface ProviderConnectionGroup {
  id: string;
  name: string;
  source: string;
  baseUrl: string;
  apiKey?: string;
  apiKeyConfigured: boolean;
  verified: boolean;
  models: ProviderModel[];
}

interface AddedProvider extends ProviderOption {
  groups: ProviderConnectionGroup[];
}

interface ProviderConfigModalState {
  provider: ProviderOption | AddedProvider;
  group?: ProviderConnectionGroup;
}

interface AlgorithmProviderConfig {
  source: string;
  baseUrl: string;
  apiKey?: string;
}

interface ModuleConfig {
  key: ModelCapability;
  title: string;
  subtitle: string;
  required?: boolean;
  restricted?: boolean;
}

interface ProviderConfigFormValues {
  name?: string;
  apiKey?: string;
  baseUrl?: string;
}

interface CustomModelModalState {
  provider: AddedProvider;
  group: ProviderConnectionGroup;
}

interface CustomModelFormValues {
  providerId: string;
  groupId: string;
  name: string;
  capability: ModelCapability;
}

interface SelectedModelApiItem {
  base_url?: string;
  group_name: string;
  model_id: string;
  model_type: string;
  name: string;
  provider_name: string;
  user_model_provider_group_id: string;
  user_model_provider_id: string;
}

const capabilityLabels: Record<ModelCapability, string> = {
  LLM_CHAT: "大模型",
  EMBEDDING: "Embedding",
  VLM: "图文模型",
  RERANK: "Rerank",
  ASR: "语音转文字",
  TTS: "文字转语音",
  TEXT_TO_IMAGE: "文生图",
  MULTIMODAL_EMBEDDING: "多模态向量",
  IMAGE_EDITING: "图像编辑",
  LLM_SELF_EVOLUTION: "自进化",
};

const moduleConfigs: ModuleConfig[] = [
  {
    key: "LLM_CHAT",
    title: "大模型（对话）",
    subtitle: "负责聊天、问答与核心推理，是系统功能的必配项。",
    required: true,
  },
  {
    key: "EMBEDDING",
    title: "向量模型",
    subtitle: "用于知识库向量化与检索召回，当前只能从平台限定模型中选择。",
    required: true,
    restricted: true,
  },
  {
    key: "VLM",
    title: "图文模型",
    subtitle: "用于图片理解、多模态问答与视觉内容分析。",
  },
  {
    key: "RERANK",
    title: "重排序模型",
    subtitle: "对召回结果二次排序，提升检索答案相关性。",
  },
  {
    key: "ASR",
    title: "语音转文字",
    subtitle: "将音频输入转换为文本，支撑语音问答场景。",
  },
  {
    key: "TTS",
    title: "文字转语音",
    subtitle: "将回答播报为语音，支撑语音输出场景。",
  },
  {
    key: "TEXT_TO_IMAGE",
    title: "文生图",
    subtitle: "根据文本生成图片，用于创作与可视化扩展。",
  },
  {
    key: "LLM_SELF_EVOLUTION",
    title: "大模型（自进化）",
    subtitle: "用于记忆抽取、策略反思与系统自进化任务。",
  },
];

const builtInProviders: ProviderOption[] = [
  {
    id: "tongyi",
    name: "Tongyi-Qianwen",
    brand: "通义",
    headline: "覆盖文本、向量、多模态、语音与重排序能力，适合作为默认全能供应商。",
    source: "tongyi",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    capabilities: ["LLM_CHAT", "EMBEDDING", "VLM", "RERANK", "ASR", "TTS", "TEXT_TO_IMAGE"],
    models: [
      { id: "qwen-plus", name: "qwen-plus", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "deepseek-r1", name: "deepseek-r1", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "text-embedding-v2", name: "text-embedding-v2", capability: "EMBEDDING", builtIn: true, enabled: true },
      { id: "qwen-vl-max", name: "qwen-vl-max", capability: "VLM", builtIn: true, enabled: true },
      { id: "gte-rerank", name: "gte-rerank", capability: "RERANK", builtIn: true, enabled: true },
      { id: "qwen3-asr-flash", name: "qwen3-asr-flash", capability: "ASR", builtIn: true, enabled: true },
      { id: "sambert-zhide-v1", name: "sambert-zhide-v1", capability: "TTS", builtIn: true, enabled: true },
      { id: "wanx2-1-t2i-turbo", name: "wanx2.1-t2i-turbo", capability: "TEXT_TO_IMAGE", builtIn: true, enabled: true },
    ],
  },
  {
    id: "openai",
    name: "OpenAI",
    brand: "◎",
    headline: "通用模型生态完整，适合接入对话、向量、语音与多模态任务。",
    source: "openai",
    baseUrl: "https://api.openai.com/v1",
    capabilities: ["LLM_CHAT", "EMBEDDING", "VLM", "TTS", "ASR"],
    models: [
      { id: "gpt-4-1", name: "gpt-4.1", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "gpt-4o", name: "gpt-4o", capability: "VLM", builtIn: true, enabled: true },
      { id: "text-embedding-3-large", name: "text-embedding-3-large", capability: "EMBEDDING", builtIn: true, enabled: true },
      { id: "whisper-1", name: "whisper-1", capability: "ASR", builtIn: true, enabled: true },
      { id: "gpt-4o-mini-tts", name: "gpt-4o-mini-tts", capability: "TTS", builtIn: true, enabled: true },
    ],
  },
  {
    id: "anthropic",
    name: "Anthropic",
    brand: "AI",
    headline: "长文本和稳健推理体验突出，适合高质量文本对话场景。",
    source: "anthropic",
    baseUrl: "https://api.anthropic.com",
    capabilities: ["LLM_CHAT", "VLM"],
    models: [
      { id: "claude-sonnet-4-5", name: "claude-sonnet-4.5", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "claude-opus-4-1", name: "claude-opus-4.1", capability: "LLM_CHAT", builtIn: true, enabled: true },
    ],
  },
  {
    id: "gemini",
    name: "Gemini",
    brand: "✦",
    headline: "视觉、搜索增强与跨模态协作能力均衡。",
    source: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    capabilities: ["LLM_CHAT", "EMBEDDING", "VLM"],
    models: [
      { id: "gemini-2-5-pro", name: "gemini-2.5-pro", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "gemini-2-5-flash", name: "gemini-2.5-flash", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "gemini-embedding-001", name: "gemini-embedding-001", capability: "EMBEDDING", builtIn: true, enabled: true },
    ],
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    brand: "DS",
    headline: "推理模型性价比高，适合默认问答主模型或自进化任务。",
    source: "deepseek",
    baseUrl: "https://api.deepseek.com",
    capabilities: ["LLM_CHAT", "LLM_SELF_EVOLUTION"],
    models: [
      { id: "deepseek-chat", name: "deepseek-chat", capability: "LLM_CHAT", builtIn: true, enabled: true },
      { id: "deepseek-reasoner", name: "deepseek-reasoner", capability: "LLM_SELF_EVOLUTION", builtIn: true, enabled: true },
    ],
  },
];

type SelectedModels = Partial<Record<ModelCapability, string>>;

type ModelOptionItem = {
  provider: ProviderOption;
  group: ProviderConnectionGroup;
  model: ProviderModel;
  algorithmConfig: AlgorithmProviderConfig;
  value: string;
};

function createConnectionGroup(provider: ProviderOption, overrides: Partial<ProviderConnectionGroup> = {}): ProviderConnectionGroup {
  return {
    id: overrides.id || `${provider.id}-default`,
    name: overrides.name || provider.name,
    source: provider.source,
    baseUrl: overrides.baseUrl || provider.baseUrl,
    apiKey: overrides.apiKey,
    apiKeyConfigured: overrides.apiKeyConfigured ?? false,
    verified: overrides.verified ?? false,
    models: overrides.models || provider.models.map((model) => ({ ...model })),
  };
}

const getModelValue = (providerId: string, groupId: string, modelId: string) => `${providerId}:${groupId}:${modelId}`;

const parseModelValue = (value?: string) => {
  const [providerId, groupId, ...modelIdParts] = String(value || "").split(":");
  return {
    providerId,
    groupId,
    modelId: modelIdParts.join(":"),
  };
};

const getAlgorithmProviderConfig = (
  provider: AddedProvider,
  group: ProviderConnectionGroup
): AlgorithmProviderConfig => ({
  source: provider.source,
  baseUrl: group.baseUrl,
  apiKey: group.apiKeyConfigured ? "********" : undefined,
});

enum ModelProviderModelType {
  VLM = "VLM",
  LLM = "llm",
  Embedding = "embedding",
  MultimodalEmbedding = "multimodal_embedding",
  TextToImage = "text2image",
  TTS = "tts",
  STT = "stt",
  Rerank = "rerank",
  ImageEditing = "image_editing",
}

const modelTypeByCapability: Record<ModelCapability, ModelProviderModelType> = {
  LLM_CHAT: ModelProviderModelType.LLM,
  EMBEDDING: ModelProviderModelType.Embedding,
  VLM: ModelProviderModelType.VLM,
  RERANK: ModelProviderModelType.Rerank,
  ASR: ModelProviderModelType.STT,
  TTS: ModelProviderModelType.TTS,
  TEXT_TO_IMAGE: ModelProviderModelType.TextToImage,
  MULTIMODAL_EMBEDDING: ModelProviderModelType.MultimodalEmbedding,
  IMAGE_EDITING: ModelProviderModelType.ImageEditing,
  LLM_SELF_EVOLUTION: ModelProviderModelType.LLM,
};

function normalizeProviderKey(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "provider";
}

function getProviderBrand(name: string) {
  const trimmed = name.trim();
  if (!trimmed) return "AI";
  if (/openai/i.test(trimmed)) return "◎";
  return trimmed
    .split(/[\s-]+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function getProviderLogoUrl(name: string) {
  const normalized = name.trim().toLowerCase();
  const domainMap: Array<[RegExp, string]> = [
    [/claude|anthropic/, "anthropic.com"],
    [/deepseek/, "deepseek.com"],
    [/doubao|volc|ark/, "volcengine.com"],
    [/glm|bigmodel|zhipu/, "bigmodel.cn"],
    [/kimi|moonshot/, "moonshot.cn"],
    [/minimax/, "minimaxi.com"],
    [/openai/, "openai.com"],
    [/qwen|tongyi|通义/, "qwen.ai"],
    [/sensenova|sensecore|商汤/, "sensenova.cn"],
    [/siliconflow/, "siliconflow.cn"],
  ];
  const match = domainMap.find(([pattern]) => pattern.test(normalized));
  if (!match) return undefined;
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(match[1])}&sz=96`;
}

function mapModelTypeToCapability(modelType?: string): ModelCapability {
  const normalized = (modelType || "").toLowerCase();
  if (normalized === ModelProviderModelType.MultimodalEmbedding) return "MULTIMODAL_EMBEDDING";
  if (normalized.includes("embedding")) return "EMBEDDING";
  if (normalized.includes("rerank")) return "RERANK";
  if (normalized === ModelProviderModelType.STT || normalized === "asr") return "ASR";
  if (normalized === ModelProviderModelType.TTS) return "TTS";
  if (normalized === ModelProviderModelType.ImageEditing) return "IMAGE_EDITING";
  if (normalized === ModelProviderModelType.TextToImage) return "TEXT_TO_IMAGE";
  if (normalized === ModelProviderModelType.VLM.toLowerCase() || normalized.includes("vision")) return "VLM";
  return "LLM_CHAT";
}

function getCapabilityByModelType(modelType?: string): ModelCapability | undefined {
  const normalized = (modelType || "").toLowerCase();
  return moduleConfigs.find((module) => modelTypeByCapability[module.key].toLowerCase() === normalized)?.key;
}

interface ApiEnvelope<T> {
  code?: number;
  message?: string;
  data?: T;
}

interface ApiProvider {
  id: string;
  name: string;
  description?: string;
  base_url?: string;
}

interface ApiGroup {
  id: string;
  name: string;
  base_url?: string;
  api_key?: string;
  is_verified?: boolean;
  user_model_provider_id: string;
}

interface ApiModel {
  id: string;
  name: string;
  model_type?: string;
  is_default?: boolean;
}

function getApiBaseUrl() {
  return `${BASE_URL || window.location.origin}/api/core`;
}

function getRequestHeaders() {
  return {
    "Content-Type": "application/json",
    ...AgentAppsAuth.getAuthHeaders(),
  };
}

function unwrapResponse<T>(payload: ApiEnvelope<T> | T): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as ApiEnvelope<T>).data as T;
  }
  return payload as T;
}

async function modelProviderRequest<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  data?: unknown,
  options?: RawAxiosRequestConfig
) {
  const response = await axiosInstance.request<ApiEnvelope<T> | T>({
    method,
    url: `${getApiBaseUrl()}${path}`,
    data,
    headers: getRequestHeaders(),
    ...options,
  });
  return unwrapResponse<T>(response.data);
}

function mapApiProvider(provider: ApiProvider): ProviderOption {
  return {
    id: provider.id,
    name: provider.name,
    brand: getProviderBrand(provider.name),
    logoUrl: getProviderLogoUrl(provider.name),
    headline: provider.description || "系统内置模型供应商，可配置连接分组后使用。",
    source: provider.name,
    baseUrl: provider.base_url || "",
    capabilities: [
      "LLM_CHAT",
      "EMBEDDING",
      "MULTIMODAL_EMBEDDING",
      "VLM",
      "RERANK",
      "ASR",
      "TTS",
      "TEXT_TO_IMAGE",
      "IMAGE_EDITING",
    ],
    models: [],
  };
}

function mapApiGroup(
  provider: ProviderOption,
  group: ApiGroup | ProviderConnectionGroup,
  models: ApiModel[]
): ProviderConnectionGroup {
  const isApiGroup = "base_url" in group || "api_key" in group || "is_verified" in group;

  return createConnectionGroup(provider, {
    id: group.id,
    name: group.name,
    baseUrl: isApiGroup ? (group as ApiGroup).base_url || provider.baseUrl : (group as ProviderConnectionGroup).baseUrl || provider.baseUrl,
    apiKey: isApiGroup ? (group as ApiGroup).api_key : (group as ProviderConnectionGroup).apiKey,
    apiKeyConfigured: isApiGroup ? Boolean((group as ApiGroup).api_key) : (group as ProviderConnectionGroup).apiKeyConfigured,
    verified: isApiGroup ? Boolean((group as ApiGroup).is_verified) : (group as ProviderConnectionGroup).verified,
    models: models.map((model) => ({
      id: model.id,
      name: model.name,
      capability: mapModelTypeToCapability(model.model_type),
      builtIn: Boolean(model.is_default),
      enabled: true,
    })),
  });
}

function ProviderLogo({ provider, compact = false }: { provider: ProviderOption; compact?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`model-provider-logo is-${normalizeProviderKey(provider.name)}${compact ? " is-compact" : ""}`}
    >
      <span className="model-provider-logo-fallback">{provider.brand}</span>
      {provider.logoUrl ? (
        <img
          alt=""
          loading="lazy"
          src={provider.logoUrl}
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
    </span>
  );
}

function CapabilityTag({ capability, active = false }: { capability: ModelCapability; active?: boolean }) {
  return (
    <Tag className={`model-provider-capability${active ? " is-active" : ""}`}>
      {capabilityLabels[capability]}
    </Tag>
  );
}

function normalizeModelName(value: string) {
  return value.trim().toLowerCase();
}

function normalizeFormText(value?: string) {
  return value?.trim() || "";
}

function renderDescriptionWithLinks(description: string) {
  const parts = description.split(/(https?:\/\/[^\s，。；、）)]+)/g);

  return parts.map((part, index) => {
    if (/^https?:\/\//.test(part)) {
      return (
        <a
          href={part}
          key={`${part}-${index}`}
          rel="noreferrer"
          target="_blank"
          onClick={(event) => event.stopPropagation()}
        >
          {part}
        </a>
      );
    }

    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function isDefaultProviderBaseUrl(provider: Pick<ProviderOption, "baseUrl">, baseUrl?: string) {
  return normalizeFormText(baseUrl) === normalizeFormText(provider.baseUrl);
}

export default function ModelProviderPage() {
  const [providerConfigForm] = Form.useForm<ProviderConfigFormValues>();
  const [customModelForm] = Form.useForm<CustomModelFormValues>();

  const [providerOptions, setProviderOptions] = useState<ProviderOption[]>(builtInProviders);
  const [addedProviderList, setAddedProviderList] = useState<AddedProvider[]>([]);
  const [configModal, setConfigModal] = useState<ProviderConfigModalState | null>(null);
  const [customModelModal, setCustomModelModal] = useState<CustomModelModalState | null>(null);
  const [expandedProviderIds, setExpandedProviderIds] = useState<Record<string, boolean>>({});
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [providerConfigSaving, setProviderConfigSaving] = useState(false);
  const [verifyingGroupIds, setVerifyingGroupIds] = useState<Record<string, boolean>>({});
  const [expandedGroupIds, setExpandedGroupIds] = useState<Record<string, boolean>>({});
  const [loadingGroupModelIds, setLoadingGroupModelIds] = useState<Record<string, boolean>>({});
  const [selectedModels, setSelectedModels] = useState<SelectedModels>({});
  const [moduleModelOptions, setModuleModelOptions] = useState<Partial<Record<ModelCapability, ModelOptionItem[]>>>({});
  const [moduleModelLoading, setModuleModelLoading] = useState<Partial<Record<ModelCapability, boolean>>>({});
  const watchedProviderBaseUrl = Form.useWatch("baseUrl", providerConfigForm);
  const configProvider = configModal?.provider || null;
  const baseUrlChanged = configProvider
    ? !isDefaultProviderBaseUrl(
        configProvider,
        watchedProviderBaseUrl ?? providerConfigForm.getFieldValue("baseUrl") ?? configProvider.baseUrl
      )
    : false;
  const apiKeyRequired = !!configProvider && !baseUrlChanged;

  const loadModelProviders = async () => {
    setLoading(true);
    try {
      const providerData = await modelProviderRequest<{ providers?: ApiProvider[] }>("GET", "/model_providers");
      const providers = (providerData.providers || []).map(mapApiProvider);
      setProviderOptions(providers);

      const withGroupsData = await modelProviderRequest<{ providers?: ApiProvider[] }>("GET", "/model_providers:with_groups");
      const addedIds = new Set((withGroupsData.providers || []).map((provider) => provider.id));
      const addedProviders = await Promise.all(
        providers
          .filter((provider) => addedIds.has(provider.id))
          .map(async (provider): Promise<AddedProvider> => {
            const groupData = await modelProviderRequest<{ groups?: ApiGroup[] }>(
              "GET",
              `/model_providers/${encodeURIComponent(provider.id)}/groups`
            );
            const groups = (groupData.groups || []).map((group) => mapApiGroup(provider, group, []));
            return { ...provider, groups };
          })
      );

      setAddedProviderList(addedProviders);
      setExpandedProviderIds((current) => {
        const next = { ...current };
        addedProviders.forEach((provider, index) => {
          if (next[provider.id] === undefined) {
            next[provider.id] = index === 0;
          }
        });
        return next;
      });
      const selectedData = await modelProviderRequest<{ selections?: SelectedModelApiItem[] }>(
        "GET",
        "/model_providers/selected_models"
      );
      const nextSelectedModels: SelectedModels = {};
      const selectedOptions: Partial<Record<ModelCapability, ModelOptionItem[]>> = {};
      (selectedData.selections || []).forEach((selection) => {
        const capability = getCapabilityByModelType(selection.model_type);
        if (!capability) {
          return;
        }
        const provider =
          providers.find((item) => item.id === selection.user_model_provider_id) ||
          mapApiProvider({
            id: selection.user_model_provider_id,
            name: selection.provider_name,
            base_url: selection.base_url,
          });
        const group = createConnectionGroup(provider, {
          id: selection.user_model_provider_group_id,
          name: selection.group_name,
          baseUrl: selection.base_url || provider.baseUrl,
          verified: true,
        });
        const model: ProviderModel = {
          id: selection.model_id,
          name: selection.name,
          capability,
          builtIn: true,
          enabled: true,
        };
        const option = {
          provider,
          group,
          model,
          algorithmConfig: getAlgorithmProviderConfig({ ...provider, groups: [group] }, group),
          value: getModelValue(provider.id, group.id, model.id),
        };
        nextSelectedModels[capability] = option.value;
        selectedOptions[capability] = [option, ...(selectedOptions[capability] || [])];
      });
      setSelectedModels(nextSelectedModels);
      setModuleModelOptions((current) => ({ ...selectedOptions, ...current }));
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "模型供应商加载失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadModelProviders();
  }, []);

  const addedProviderIds = useMemo(
    () => new Set(addedProviderList.map((provider) => provider.id)),
    [addedProviderList]
  );

  const visibleProviders = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();

    return providerOptions.filter((provider) => {
      const matchesKeyword =
        !normalizedKeyword ||
        provider.name.toLowerCase().includes(normalizedKeyword) ||
        provider.headline.toLowerCase().includes(normalizedKeyword) ||
        provider.models.some((model) => model.name.toLowerCase().includes(normalizedKeyword));

      return matchesKeyword;
    });
  }, [keyword, providerOptions]);

  const loadModuleModels = async (capability: ModelCapability, force = false) => {
    if (!force && moduleModelOptions[capability]) {
      return;
    }
    if (moduleModelLoading[capability]) {
      return;
    }

    setModuleModelLoading((current) => ({ ...current, [capability]: true }));
    try {
      const modelType = modelTypeByCapability[capability];
      const data = await modelProviderRequest<{ models?: Array<ApiModel & {
        user_model_provider_id: string;
        user_model_provider_group_id: string;
        provider_name: string;
        group_name: string;
        base_url?: string;
      }> }>("GET", `/model_providers/models?model_type=${encodeURIComponent(modelType)}`);
      const options = (data.models || []).map((model) => {
        const provider =
          providerOptions.find((item) => item.id === model.user_model_provider_id) ||
          mapApiProvider({
            id: model.user_model_provider_id,
            name: model.provider_name,
            base_url: model.base_url,
          });
        const configuredProvider = addedProviderList.find((item) => item.id === provider.id);
        const group =
          configuredProvider?.groups.find((item) => item.id === model.user_model_provider_group_id) ||
          createConnectionGroup(provider, {
            id: model.user_model_provider_group_id,
            name: model.group_name,
            baseUrl: model.base_url || provider.baseUrl,
            verified: true,
          });
        const providerModel: ProviderModel = {
          id: model.id,
          name: model.name,
          capability,
          builtIn: Boolean(model.is_default),
          enabled: true,
        };

        return {
          provider,
          group,
          model: providerModel,
          algorithmConfig: getAlgorithmProviderConfig({ ...provider, groups: [group] }, group),
          value: getModelValue(provider.id, group.id, providerModel.id),
        };
      });

      setModuleModelOptions((current) => ({ ...current, [capability]: options }));
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "模型列表加载失败"));
    } finally {
      setModuleModelLoading((current) => ({ ...current, [capability]: false }));
    }
  };

  const clearModuleModelCache = (capability?: ModelCapability) => {
    setModuleModelOptions((current) => {
      if (!capability) {
        return {};
      }
      const next = { ...current };
      delete next[capability];
      return next;
    });
  };

  useEffect(() => {
    Object.entries(selectedModels).forEach(([capability, value]) => {
      if (value && !moduleModelOptions[capability as ModelCapability]) {
        void loadModuleModels(capability as ModelCapability);
      }
    });
  }, [selectedModels, moduleModelOptions]);

  const openProviderConfig = (provider: AddedProvider | ProviderOption, group?: ProviderConnectionGroup) => {
    const configuredProvider = addedProviderList.find((item) => item.id === provider.id);
    const providerDraft = configuredProvider || provider;
    const groupDraft = group || createConnectionGroup(providerDraft);

    setConfigModal({ provider: providerDraft, group });
    providerConfigForm.setFieldsValue({
      name: groupDraft.name,
      apiKey: groupDraft.apiKeyConfigured ? "********" : "",
      baseUrl: groupDraft.baseUrl || providerDraft.baseUrl,
    });
  };

  const closeProviderConfig = () => {
    if (providerConfigSaving) {
      return;
    }
    setConfigModal(null);
    providerConfigForm.resetFields();
  };

  const saveProviderConfig = async (values: ProviderConfigFormValues) => {
    const activeConfigModal = configModal;

    if (!configProvider || !activeConfigModal || providerConfigSaving) {
      return;
    }

    const groupName = normalizeFormText(values.name);
    const baseUrl = normalizeFormText(values.baseUrl);
    const apiKey = normalizeFormText(values.apiKey);
    const isCustomBaseUrl = !isDefaultProviderBaseUrl(configProvider, baseUrl);
    const existingProvider = addedProviderList.find((provider) => provider.id === configProvider.id);
    const existingGroup = activeConfigModal.group
      ? existingProvider?.groups.find((group) => group.id === activeConfigModal.group?.id)
      : undefined;

    if (!isCustomBaseUrl && (!apiKey || (!existingGroup && apiKey === "********"))) {
      providerConfigForm.setFields([{ name: "apiKey", errors: ["请输入 API Key"] }]);
      return;
    }

    setProviderConfigSaving(true);
    try {
      const payload = {
        name: groupName || configProvider.name,
        base_url: baseUrl,
        ...(apiKey && apiKey !== "********" ? { api_key: apiKey } : {}),
      };
      const savedGroup = activeConfigModal.group
        ? await modelProviderRequest<ApiGroup>(
            "PATCH",
            `/model_providers/${encodeURIComponent(configProvider.id)}/groups/${encodeURIComponent(activeConfigModal.group.id)}`,
            payload
          )
        : await modelProviderRequest<ApiGroup>(
            "POST",
            `/model_providers/${encodeURIComponent(configProvider.id)}/groups`,
            payload
          );
      const nextGroup = mapApiGroup(configProvider, { ...savedGroup, api_key: apiKey === "********" ? existingGroup?.apiKey : apiKey }, existingGroup?.models || []);

      setAddedProviderList((current) =>
        current.some((provider) => provider.id === configProvider.id)
          ? current.map((provider) =>
              provider.id === configProvider.id
                ? {
                    ...provider,
                    groups: existingGroup
                      ? provider.groups.map((group) => (group.id === nextGroup.id ? nextGroup : group))
                      : [...provider.groups, nextGroup],
                  }
                : provider
            )
          : [
              ...current,
              {
                ...configProvider,
                groups: [nextGroup],
              },
            ]
      );
      if (!nextGroup.verified) {
        setSelectedModels((current) => {
          const next = { ...current };
          Object.entries(next).forEach(([capability, value]) => {
            const parsed = parseModelValue(value);
            if (parsed.providerId === configProvider.id && parsed.groupId === nextGroup.id) {
              delete next[capability as ModelCapability];
            }
          });
          return next;
        });
      }
      setExpandedProviderIds((current) => ({ ...current, [configProvider.id]: true }));
      clearModuleModelCache();
      message.success(`${nextGroup.name} 已保存`);
      setConfigModal(null);
      providerConfigForm.resetFields();
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "保存失败，请稍后重试"));
    } finally {
      setProviderConfigSaving(false);
    }
  };

  const addProvider = (provider: ProviderOption) => {
    openProviderConfig(provider);
  };

  const verifyProviderGroup = async (providerId: string, groupId: string) => {
    const verifyKey = `${providerId}:${groupId}`;
    if (verifyingGroupIds[verifyKey]) {
      return;
    }

    setVerifyingGroupIds((current) => ({ ...current, [verifyKey]: true }));
    try {
      const provider = addedProviderList.find((item) => item.id === providerId);
      const group = provider?.groups.find((item) => item.id === groupId);
      if (!provider || !group) {
        return;
      }
      if (!group.apiKey) {
        message.warning("请先填写 API Key 后再验证");
        return;
      }

      await modelProviderRequest<unknown>(
        "POST",
        `/model_providers/${encodeURIComponent(provider.id)}/groups/${encodeURIComponent(group.id)}:check`,
        {
          provider_name: provider.name,
          base_url: group.baseUrl,
          api_key: group.apiKey || "",
        },
        { timeout: 3 * 60 * 1000 }
      );
      setAddedProviderList((current) =>
        current.map((provider) =>
          provider.id === providerId
            ? {
                ...provider,
                groups: provider.groups.map((group) =>
                  group.id === groupId
                    ? {
                        ...group,
                        verified: true,
                      }
                    : group
                ),
              }
            : provider
        )
      );
      message.success("分组验证通过，已可用于模型配置");
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "验证失败，请检查连接配置后重试"));
    } finally {
      setVerifyingGroupIds((current) => {
        const next = { ...current };
        delete next[verifyKey];
        return next;
      });
    }
  };

  const deleteProviderGroup = async (providerId: string, group: ProviderConnectionGroup) => {
    const provider = addedProviderList.find((item) => item.id === providerId);
    if (!provider) {
      return;
    }

    try {
      await modelProviderRequest("DELETE", `/model_providers/${encodeURIComponent(providerId)}/groups/${encodeURIComponent(group.id)}`);
      setAddedProviderList((current) =>
        current
          .map((item) =>
            item.id === providerId
              ? {
                  ...item,
                  groups: item.groups.filter((candidate) => candidate.id !== group.id),
                }
              : item
          )
          .filter((item) => item.groups.length > 0)
      );
      setSelectedModels((current) => {
        const next = { ...current };
        Object.entries(next).forEach(([capability, value]) => {
          const parsed = parseModelValue(value);
          if (parsed.providerId === providerId && parsed.groupId === group.id) {
            delete next[capability as ModelCapability];
          }
        });
        return next;
      });
      setExpandedGroupIds((current) => {
        const next = { ...current };
        delete next[`${providerId}:${group.id}`];
        return next;
      });
      clearModuleModelCache();
      message.success(`${group.name} 已移除`);
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "删除分组失败"));
    }
  };

  const deleteProvider = async (provider: AddedProvider) => {
    try {
      await Promise.all(
        provider.groups.map((group) =>
          modelProviderRequest("DELETE", `/model_providers/${encodeURIComponent(provider.id)}/groups/${encodeURIComponent(group.id)}`)
        )
      );
      setAddedProviderList((current) => current.filter((item) => item.id !== provider.id));
      setExpandedProviderIds((current) => {
        const next = { ...current };
        delete next[provider.id];
        return next;
      });
      setExpandedGroupIds((current) => {
        const next = { ...current };
        provider.groups.forEach((group) => {
          delete next[`${provider.id}:${group.id}`];
        });
        return next;
      });
      setSelectedModels((current) => {
        const next = { ...current };
        Object.entries(next).forEach(([capability, value]) => {
          if (parseModelValue(value).providerId === provider.id) {
            delete next[capability as ModelCapability];
          }
        });
        return next;
      });
      clearModuleModelCache();
      message.success(`${provider.name} 已移除`);
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "移除供应商失败"));
    }
  };

  const loadGroupModels = async (providerId: string, groupId: string) => {
    const provider = addedProviderList.find((item) => item.id === providerId);
    const group = provider?.groups.find((item) => item.id === groupId);
    const groupKey = `${providerId}:${groupId}`;
    if (!provider || !group || loadingGroupModelIds[groupKey]) {
      return;
    }

    setLoadingGroupModelIds((current) => ({ ...current, [groupKey]: true }));
    try {
      const modelData = await modelProviderRequest<{ models?: ApiModel[] }>(
        "GET",
        `/model_providers/${encodeURIComponent(provider.id)}/groups/${encodeURIComponent(group.id)}/models`
      );
      const nextGroup = mapApiGroup(provider, group, modelData.models || []);
      setAddedProviderList((current) =>
        current.map((item) =>
          item.id === providerId
            ? {
                ...item,
                groups: item.groups.map((candidate) => (candidate.id === groupId ? nextGroup : candidate)),
              }
            : item
        )
      );
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "模型列表加载失败"));
    } finally {
      setLoadingGroupModelIds((current) => {
        const next = { ...current };
        delete next[groupKey];
        return next;
      });
    }
  };

  const toggleGroupModels = async (providerId: string, groupId: string) => {
    const groupKey = `${providerId}:${groupId}`;
    const willExpand = !expandedGroupIds[groupKey];
    if (willExpand) {
      await loadGroupModels(providerId, groupId);
    }
    setExpandedGroupIds((current) => ({ ...current, [groupKey]: willExpand }));
  };

  const toggleProviderModels = async (providerId: string) => {
    const willExpand = !expandedProviderIds[providerId];
    setExpandedProviderIds((current) => ({
      ...current,
      [providerId]: willExpand,
    }));
  };

  const openCustomModelModal = (provider: AddedProvider, group: ProviderConnectionGroup) => {
    setCustomModelModal({ provider, group });
    customModelForm.setFieldsValue({
      providerId: provider.id,
      groupId: group.id,
      capability: provider.capabilities[0] || "LLM_CHAT",
      name: "",
    });
  };

  const closeCustomModelModal = () => {
    setCustomModelModal(null);
    customModelForm.resetFields();
  };

  const addCustomModel = async (values: CustomModelFormValues) => {
    const provider = addedProviderList.find((item) => item.id === values.providerId);
    const group = provider?.groups.find((item) => item.id === values.groupId);
    if (!provider || !group) {
      return;
    }

    const normalizedName = normalizeModelName(values.name);
    const duplicated = group.models.some((model) => normalizeModelName(model.name) === normalizedName);

    if (duplicated) {
      customModelForm.setFields([{ name: "name", errors: ["不能和该分组内置或已添加模型重名"] }]);
      return;
    }

    try {
      const createdModel = await modelProviderRequest<ApiModel>(
        "POST",
        `/model_providers/${encodeURIComponent(provider.id)}/groups/${encodeURIComponent(group.id)}/models`,
        {
          name: values.name.trim(),
          model_type: modelTypeByCapability[values.capability],
        }
      );
      const nextModel: ProviderModel = {
        id: createdModel.id,
        name: createdModel.name,
        capability: mapModelTypeToCapability(createdModel.model_type || modelTypeByCapability[values.capability]),
        builtIn: Boolean(createdModel.is_default),
        enabled: true,
      };
      setAddedProviderList((current) =>
        current.map((item) =>
          item.id === provider.id
            ? {
                ...item,
                groups: item.groups.map((candidate) =>
                  candidate.id === group.id
                    ? {
                        ...candidate,
                        models: [...candidate.models, nextModel],
                      }
                    : candidate
                ),
              }
            : item
        )
      );
      clearModuleModelCache(values.capability);
      message.success("模型已添加");
      closeCustomModelModal();
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "模型添加失败"));
    }
  };

  const deleteCustomModel = async (providerId: string, groupId: string, model: ProviderModel) => {
    try {
      await modelProviderRequest(
        "DELETE",
        `/model_providers/${encodeURIComponent(providerId)}/groups/${encodeURIComponent(groupId)}/models/${encodeURIComponent(model.id)}`
      );
      setAddedProviderList((current) =>
        current.map((provider) =>
          provider.id === providerId
            ? {
                ...provider,
                groups: provider.groups.map((group) =>
                  group.id === groupId
                    ? {
                        ...group,
                        models: group.models.filter((item) => item.id !== model.id),
                      }
                    : group
                ),
              }
            : provider
        )
      );
      setSelectedModels((current) => {
        const next = { ...current };
        Object.entries(next).forEach(([capability, selectedValue]) => {
          const parsed = parseModelValue(selectedValue);
          if (parsed.providerId === providerId && parsed.groupId === groupId && parsed.modelId === model.id) {
            delete next[capability as ModelCapability];
          }
        });
        return next;
      });
      clearModuleModelCache(model.capability);
      message.success("模型已删除");
    } catch (error) {
      message.error(getLocalizedErrorMessage(error, "模型删除失败"));
    }
  };

  const saveSelectedModel = async (capability: ModelCapability, value?: string) => {
    if (!value) {
      return;
    }
    const { modelId } = parseModelValue(value);
    await modelProviderRequest<{ selections?: SelectedModelApiItem[] }>("PUT", "/model_providers/selected_models", {
      selections: [
        {
          model_type: modelTypeByCapability[capability],
          model_id: modelId,
        },
      ],
    });
  };

  const applyModelSelection = (capability: ModelCapability, value?: string) => {
    setSelectedModels((current) => ({
      ...current,
      [capability]: value,
    }));
    void saveSelectedModel(capability, value).catch((error) => {
      message.error(getLocalizedErrorMessage(error, "默认模型保存失败"));
    });
  };

  const handleModelSelection = (capability: ModelCapability, value?: string) => {
    const previousValue = selectedModels[capability];
    if (capability === "EMBEDDING" && previousValue && previousValue !== value) {
      Modal.confirm({
        title: "向量模型变更提醒",
        content: "切换向量模型后，知识库检索服务将暂时不可用，直到向量全部重新计算完成。",
        okText: "确认切换",
        cancelText: "暂不切换",
        onOk: () => {
          applyModelSelection(capability, value);
        },
      });
      return;
    }

    applyModelSelection(capability, value);
  };

  return (
    <main className="model-provider-page">
      <section className="model-provider-shell">
        <div className="model-provider-main-panel">
          <section className="model-provider-config-panel" aria-label="模块默认模型配置">
            <div className="model-provider-panel-title-row">
              <div>
                <h2>模块默认模型</h2>
                <p>不同模块可以选择不同模型；必配项未完成时，系统功能将受限。</p>
              </div>
            </div>

            <Alert
              className="model-provider-inline-alert"
              message="向量模型当前仅允许从平台限定的供应商和模型中选择；后续名单确定后可直接收敛这里的选项。"
              showIcon
              type="info"
            />

            <div className="model-provider-default-list">
              {moduleConfigs.map((module) => {
                const options = moduleModelOptions[module.key] || [];
                const optionLoading = Boolean(moduleModelLoading[module.key]);

                return (
                  <div className="model-provider-default-row" key={module.key}>
                    <div className="model-provider-default-meta">
                      <label
                        className="model-provider-default-title"
                        htmlFor={`model-provider-${module.key.toLowerCase()}`}
                      >
                        {module.required ? <span className="is-required">*</span> : null}
                        <span>{module.title}</span>
                      </label>
                      <Tooltip placement="top" title={module.subtitle}>
                        <button
                          aria-label={`${module.title} 说明`}
                          className="model-provider-default-help"
                          type="button"
                        >
                          <QuestionCircleOutlined />
                        </button>
                      </Tooltip>
                      {module.restricted ? <Tag className="model-provider-limited-tag">限定</Tag> : null}
                    </div>

                    <Select
                      allowClear={!module.required}
                      className="model-provider-model-select"
                      id={`model-provider-${module.key.toLowerCase()}`}
                      listHeight={340}
                      optionLabelProp="label"
                      placeholder={module.required ? "请选择必配模型" : "可选配置"}
                      popupClassName="model-provider-select-dropdown"
                      suffixIcon={<DownOutlined className="model-provider-select-caret" />}
                      value={selectedModels[module.key]}
                      onChange={(value) => handleModelSelection(module.key, value)}
                      onDropdownVisibleChange={(open) => {
                        if (open) {
                          void loadModuleModels(module.key);
                        }
                      }}
                      loading={optionLoading}
                      notFoundContent={optionLoading ? "加载中..." : "暂无可选模型"}
                    >
                      {options.map(({ provider, group, model, value }) => (
                        <Select.Option
                          key={value}
                          label={
                            <span className="model-provider-select-value">
                              <ProviderLogo provider={provider} compact />
                              <span className="model-provider-select-value-text">
                                {model.name} · {group.name}
                              </span>
                            </span>
                          }
                          value={value}
                        >
                          <span className="model-provider-select-option">
                            <ProviderLogo provider={provider} compact />
                            <span className="model-provider-select-copy">
                              <strong>{model.name}</strong>
                              <small>
                                {provider.name} / {group.name}
                                {model.builtIn ? " · 内置模型" : " · 自定义模型"}
                              </small>
                            </span>
                          </span>
                        </Select.Option>
                      ))}
                    </Select>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="model-provider-added-section">
            <div className="model-provider-panel-heading">
              <h2>我的供应商分组与模型</h2>
              <p>一个供应商可以维护多个连接分组；分组保存后需验证通过，才会进入默认模型选择。</p>
            </div>

            <div className="model-provider-added-list">
              {addedProviderList.length ? (
                addedProviderList.map((provider) => {
                  const isExpanded = !!expandedProviderIds[provider.id];
                  const modelListId = `model-provider-${provider.id}-models`;

                  return (
                    <article
                      className={`model-provider-added-card${isExpanded ? " is-expanded" : ""}`}
                      key={provider.id}
                    >
                      <div className="model-provider-added-summary">
                        <div className="model-provider-added-brand">
                          <ProviderLogo provider={provider} />
                          <div>
                            <strong>{provider.name}</strong>
                            <span>
                              source: {provider.source} · {provider.groups.length} 个分组
                            </span>
                          </div>
                        </div>

                        <div className="model-provider-added-actions">
                          <span className="model-provider-connection-badge">
                            <CheckCircleFilled />
                            {provider.groups.filter((group) => group.verified).length} 个可用
                          </span>
                          <Button icon={<PlusCircleOutlined />} onClick={() => openProviderConfig(provider)}>
                            新增分组
                          </Button>
                          <Button
                            aria-controls={modelListId}
                            aria-expanded={isExpanded}
                            className="model-provider-expand-button"
                            onClick={() => void toggleProviderModels(provider.id)}
                          >
                            {isExpanded ? "隐藏模型" : "展示模型"}
                            {isExpanded ? <UpOutlined /> : <DownOutlined />}
                          </Button>
                          <Popconfirm
                            cancelText="取消"
                            okButtonProps={{ danger: true }}
                            okText="移除"
                            title={`确认移除 ${provider.name}？`}
                            description="移除后，使用该供应商的模块选择会被清空。"
                            onConfirm={() => deleteProvider(provider)}
                          >
                            <Button aria-label={`移除 ${provider.name}`} danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </div>
                      </div>

                      {isExpanded ? (
                        <div
                          aria-label={`${provider.name} 模型列表`}
                          className="model-provider-added-models"
                          id={modelListId}
                        >
                          <div className="model-provider-added-tags" aria-label={`${provider.name} 支持能力`}>
                            {provider.capabilities.map((capability) => (
                              <CapabilityTag capability={capability} key={capability} />
                            ))}
                          </div>

                          <div className="model-provider-group-rows" aria-label={`${provider.name} 连接分组`}>
                            {provider.groups.map((group) => {
                              const verifyKey = `${provider.id}:${group.id}`;

                              return (
                                <div className="model-provider-group-row" key={group.id}>
                                  <div className="model-provider-group-header">
                                    <div className="model-provider-group-meta">
                                      <div className="model-provider-group-title-row">
                                        <strong>{group.name}</strong>
                                        <Tag className="model-provider-source-tag">source: {group.source}</Tag>
                                        <Tag className={group.verified ? "model-provider-verified-tag" : "model-provider-pending-tag"}>
                                          {group.verified ? "已验证" : "待验证"}
                                        </Tag>
                                      </div>
                                      <span>{group.baseUrl}</span>
                                    </div>

                                    <div className="model-provider-group-actions">
                                      <Button
                                        className="model-provider-group-toggle"
                                        loading={!!loadingGroupModelIds[`${provider.id}:${group.id}`]}
                                        onClick={() => void toggleGroupModels(provider.id, group.id)}
                                      >
                                        {expandedGroupIds[`${provider.id}:${group.id}`] ? "隐藏模型" : "展示模型"}
                                        {expandedGroupIds[`${provider.id}:${group.id}`] ? <UpOutlined /> : <DownOutlined />}
                                      </Button>
                                      <Button icon={<PlusCircleOutlined />} onClick={() => openCustomModelModal(provider, group)}>
                                        添加模型
                                      </Button>
                                      <Button icon={<EditOutlined />} onClick={() => openProviderConfig(provider, group)}>
                                        编辑
                                      </Button>
                                      <Button
                                        icon={<KeyOutlined />}
                                        loading={!!verifyingGroupIds[verifyKey]}
                                        type={group.verified ? "default" : "primary"}
                                        onClick={() => verifyProviderGroup(provider.id, group.id)}
                                      >
                                        {group.verified ? "重新验证" : "验证"}
                                      </Button>
                                      <Popconfirm
                                        cancelText="取消"
                                        okButtonProps={{ danger: true }}
                                        okText="删除"
                                        title={`确认删除 ${group.name}？`}
                                        description="删除后，引用该分组的模块配置会被清空。"
                                        onConfirm={() => deleteProviderGroup(provider.id, group)}
                                      >
                                        <Button aria-label={`删除 ${group.name}`} danger icon={<DeleteOutlined />} />
                                      </Popconfirm>
                                    </div>
                                  </div>

                                  {expandedGroupIds[`${provider.id}:${group.id}`] ? (
                                    <div className="model-provider-branch-model-rows" aria-label={`${group.name} 模型列表`}>
                                      {group.models.length ? (
                                        group.models.map((model) => (
                                          <div className="model-provider-model-row" key={model.id}>
                                            <div className="model-provider-model-meta">
                                              <strong>{model.name}</strong>
                                              <CapabilityTag capability={model.capability} />
                                              {model.builtIn ? null : <Tag className="model-provider-custom-tag">自定义</Tag>}
                                            </div>

                                            <div className="model-provider-model-actions">
                                              {model.builtIn ? (
                                                <span>不可删除</span>
                                              ) : (
                                                <Popconfirm
                                                  cancelText="取消"
                                                  okButtonProps={{ danger: true }}
                                                  okText="删除"
                                                  title={`确认删除 ${model.name}？`}
                                                  description="删除后，引用该模型的模块配置会被清空。"
                                                  onConfirm={() => deleteCustomModel(provider.id, group.id, model)}
                                                >
                                                  <Button aria-label={`删除 ${model.name}`} icon={<DeleteOutlined />} />
                                                </Popconfirm>
                                              )}
                                            </div>
                                          </div>
                                        ))
                                      ) : (
                                        <div className="model-provider-model-empty">暂无模型</div>
                                      )}
                                    </div>
                                  ) : null}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : null}
                    </article>
                  );
                })
              ) : (
                <div className="model-provider-empty-state" role="status">
                  <Empty description="暂无供应商，请从右侧添加内置供应商" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="model-provider-side-panel" aria-label="内置模型供应商">
          <div className="model-provider-side-header">
            <h2>内置供应商</h2>
            <p>供应商与内置模型清单由系统提供，你只需要配置自己的连接信息。</p>
          </div>

          <Input
            allowClear
            aria-label="搜索供应商或模型"
            disabled={loading}
            placeholder="搜索供应商或模型"
            size="large"
            suffix={<SearchOutlined />}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />

          <div className="model-provider-list">
            {visibleProviders.length ? (
              visibleProviders.map((provider) => {
                const isAdded = addedProviderIds.has(provider.id);

                return (
                  <article className={`model-provider-card${isAdded ? " is-added" : ""}`} key={provider.id}>
                    <div className="model-provider-card-header">
                      <div className="model-provider-card-brand">
                        <ProviderLogo provider={provider} />
                        <div>
                          <div className="model-provider-card-title-row">
                            <strong>{provider.name}</strong>
                            {isAdded ? <Tag className="model-provider-added-tag">已添加</Tag> : null}
                          </div>
                          <Tooltip
                            overlayClassName="model-provider-description-tooltip"
                            placement="left"
                            title={renderDescriptionWithLinks(provider.headline)}
                          >
                            <p className="model-provider-card-description">{provider.headline}</p>
                          </Tooltip>
                        </div>
                      </div>
                    </div>

                    <div className="model-provider-card-foot">
                      <Button
                        className="model-provider-add-button"
                        icon={<PlusCircleOutlined />}
                        type="primary"
                        onClick={() => addProvider(provider)}
                      >
                        {isAdded ? "新增分组" : "配置并添加"}
                      </Button>
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="model-provider-empty-state" role="status">
                <Empty description="没有找到符合条件的供应商" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            )}
          </div>
        </aside>
      </section>

      <Modal
        centered
        confirmLoading={providerConfigSaving}
        destroyOnHidden
        maskClosable={!providerConfigSaving}
        okText="保存配置"
        open={!!configModal}
        title={`${configProvider?.name || ""} 分组配置`}
        width={520}
        onCancel={closeProviderConfig}
        onOk={() => providerConfigForm.submit()}
      >
        <Form<ProviderConfigFormValues>
          className="model-provider-form"
          form={providerConfigForm}
          layout="vertical"
          onFinish={saveProviderConfig}
        >
          <Form.Item
            extra="默认使用供应商名称；保存后会在分组列表展示。"
            label="分组名称"
            name="name"
            normalize={(value: string | undefined) => value?.trim()}
            rules={[
              { required: true, message: "请输入分组名称" },
              { max: 80, message: "分组名称不能超过 80 个字符" },
            ]}
          >
            <Input maxLength={80} placeholder={configProvider?.name || "请输入分组名称"} />
          </Form.Item>

          <Form.Item
            extra={baseUrlChanged ? "当前已改为自定义 Base URL，API Key 可不填写。" : "Base URL 必填，默认值来自供应商内置配置。"}
            label="Base URL"
            name="baseUrl"
            normalize={(value: string | undefined) => value?.trim()}
            rules={[
              { required: true, message: "请输入 Base URL" },
              { type: "url", message: "请输入有效的 URL" },
              { max: 512, message: "Base URL 不能超过 512 个字符" },
            ]}
          >
            <Input maxLength={512} placeholder="https://api.example.com/v1" />
          </Form.Item>

          <Form.Item
            dependencies={["baseUrl"]}
            extra={baseUrlChanged ? "自定义 Base URL 可不填写 API Key；已配置分组可保留掩码不变。" : "默认 Base URL 下 API Key 必填；已配置分组可保留掩码不变。"}
            label="API Key"
            name="apiKey"
            normalize={(value: string | undefined) => value?.trim()}
            required={apiKeyRequired}
            rules={[
              {
                validator: (_, value?: string) => {
                  const apiKey = normalizeFormText(value);

                  if (apiKeyRequired && !apiKey) {
                    return Promise.reject(new Error("请输入 API Key"));
                  }

                  if (apiKey.length > 512) {
                    return Promise.reject(new Error("API Key 不能超过 512 个字符"));
                  }

                  if (/\s/.test(apiKey)) {
                    return Promise.reject(new Error("API Key 不能包含空格"));
                  }

                  return Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password autoComplete="off" maxLength={512} placeholder={apiKeyRequired ? "请输入 API Key" : "可不填写"} visibilityToggle />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        centered
        destroyOnHidden
        okText="添加"
        open={!!customModelModal}
        title={`${customModelModal?.group.name || ""} 添加自定义模型`}
        width={520}
        onCancel={closeCustomModelModal}
        onOk={() => customModelForm.submit()}
      >
        <Form<CustomModelFormValues>
          className="model-provider-form"
          form={customModelForm}
          layout="vertical"
          onFinish={addCustomModel}
        >
          <Form.Item label="供应商" name="providerId" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select disabled>
              {customModelModal ? (
                <Select.Option value={customModelModal.provider.id}>{customModelModal.provider.name}</Select.Option>
              ) : null}
            </Select>
          </Form.Item>

          <Form.Item label="分组" name="groupId" rules={[{ required: true, message: "请选择分组" }]}>
            <Select disabled>
              {customModelModal ? (
                <Select.Option value={customModelModal.group.id}>{customModelModal.group.name}</Select.Option>
              ) : null}
            </Select>
          </Form.Item>

          <Form.Item
            extra="模型名称不能和该分组内置模型或已添加模型重名。"
            label="模型名称"
            name="name"
            normalize={(value: string | undefined) => value?.trim()}
            rules={[
              { required: true, message: "请输入模型名称" },
              { max: 120, message: "模型名称不能超过 120 个字符" },
              { pattern: /^[\w.-]+$/, message: "仅支持字母、数字、下划线、点和短横线" },
            ]}
          >
            <Input maxLength={120} placeholder="例如 qwen-max-latest" />
          </Form.Item>

          <Form.Item label="模型类型" name="capability" rules={[{ required: true, message: "请选择模型类型" }]}>
            <Select>
              {customModelModal?.provider.capabilities.map((capability) => (
                <Select.Option key={capability} value={capability}>
                  {capabilityLabels[capability]}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
