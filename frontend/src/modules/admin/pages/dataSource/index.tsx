import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  ApiOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  DisconnectOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  LockOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningFilled,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";

import "./index.scss";
import {
  FEISHU_DATA_SOURCE_OAUTH_CHANNEL,
  consumeFeishuDataSourceOAuthResult,
  consumeFeishuDataSourceWizardDraft,
  openCenteredPopup,
  requestFeishuDataSourceAuthorizeUrl,
  saveFeishuDataSourceWizardDraft,
  type FeishuDataSourceConnection,
  type FeishuDataSourceOAuthMessage,
  type FeishuDataSourceWizardDraft,
} from "./feishuOAuth";

const { Paragraph, Text } = Typography;

type SourceType = "local" | "s3" | "feishu" | "confluence" | "notion";
type SourceStatus = "active" | "expired" | "error" | "paused";
type ConnectionState = "connected" | "expired" | "error" | "pending";
type SyncMode = "manual" | "scheduled";
type ConflictPolicy = "overwrite" | "skip" | "versioned";
type FileSyncMode = "all" | "partial";
type OAuthState = "pending" | "waiting" | "connected" | "expired" | "error";
type FileUpdateState = "new" | "changed" | "unchanged" | "deleted";

interface PendingOAuthAttempt {
  timerId: number | null;
  previousState: OAuthState;
  previousVerified: boolean;
  previousConnection: FeishuDataSourceConnection | null;
  resolved: boolean;
}

interface SyncLogItem {
  id: string;
  time: string;
  result: "success" | "warning" | "failed";
  title: string;
  description: string;
}

interface FileCandidate {
  id: string;
  name: string;
  path: string;
  size: string;
  type: string;
  updateState: FileUpdateState;
}

interface DataSourceItem {
  id: string;
  name: string;
  type: SourceType;
  knowledgeBase: string;
  description: string;
  target: string;
  syncMode: SyncMode;
  scheduleLabel: string;
  status: SourceStatus;
  connectionState: ConnectionState;
  lastSync: string;
  nextSync: string;
  documentCount: number;
  addCount: number;
  deleteCount: number;
  changeCount: number;
  permissions: string[];
  conflictPolicy: ConflictPolicy;
  enabled: boolean;
  scopeMode: FileSyncMode;
  selectedFiles: string[];
  fileCandidates: FileCandidate[];
  logs: SyncLogItem[];
  warning?: string;
  oauthConnection?: FeishuDataSourceConnection | null;
}

interface SourceFormValues {
  name?: string;
  knowledgeBase?: string;
  description?: string;
  enabled?: boolean;
  localMode?: "fs" | "mount" | "s3mirror";
  path?: string;
  mountName?: string;
  bucket?: string;
  region?: string;
  prefix?: string;
  target?: string;
  spaceKey?: string;
  scopes?: string[];
  syncMode?: SyncMode;
  scheduleCycle?: string;
  scheduleTime?: string;
  fileSyncMode?: FileSyncMode;
  selectedFiles?: string[];
  conflictPolicy?: ConflictPolicy;
  autoScan?: boolean;
  skipInternalAssets?: boolean;
}

interface FeishuAppSetup {
  appId: string;
  appSecret: string;
}

const FEISHU_APP_SETUP_STORAGE_KEY = "lazyrag:datasource:feishu:app-setup";

const knowledgeBaseOptions = [
  "研发知识库",
  "运维知识库",
  "客服知识库",
  "法务制度库",
];

const defaultFileCandidates: FileCandidate[] = [
  {
    id: "candidate-1",
    name: "研发手册 2026.pdf",
    path: "/docs/handbook/研发手册 2026.pdf",
    size: "12.4 MB",
    type: "PDF",
    updateState: "changed",
  },
  {
    id: "candidate-2",
    name: "Q2 项目周报.md",
    path: "/wiki/project/Q2 项目周报.md",
    size: "268 KB",
    type: "Markdown",
    updateState: "unchanged",
  },
  {
    id: "candidate-3",
    name: "权限矩阵.xlsx",
    path: "/ops/security/权限矩阵.xlsx",
    size: "1.8 MB",
    type: "Excel",
    updateState: "new",
  },
];

const sourceTypeOptions: Array<{
  type: SourceType;
  icon: ReactNode;
  adminOnly?: boolean;
}> = [
  {
    type: "local",
    icon: <FolderOpenOutlined />,
    adminOnly: true,
  },
  {
    type: "feishu",
    icon: <ApiOutlined />,
  },
];

const mockSources: DataSourceItem[] = [
  {
    id: "source-feishu-rd",
    name: "飞书研发知识库",
    type: "feishu",
    knowledgeBase: "研发知识库",
    description: "同步研发团队飞书 Wiki、技术方案和评审记录",
    target: "space_rd_platform",
    syncMode: "scheduled",
    scheduleLabel: "每天 02:00 自动同步",
    status: "active",
    connectionState: "connected",
    lastSync: "2026-04-13 10:24",
    nextSync: "下一次计划执行：02:00",
    documentCount: 1284,
    addCount: 18,
    deleteCount: 2,
    changeCount: 41,
    permissions: ["只读"],
    conflictPolicy: "versioned",
    enabled: true,
    scopeMode: "all",
    selectedFiles: [],
    fileCandidates: defaultFileCandidates,
    warning: "知识库由后端创建并分配只读权限。",
    oauthConnection: {
      provider: "feishu",
      connectionId: "conn-feishu-rd",
      status: "connected",
      accountName: "研发平台服务号",
      grantedScopes: [],
      connectedAt: "2026-04-10 11:20",
      expiresAt: "2026-04-20 11:20",
      refreshExpiresAt: "2026-05-10 11:20",
      tenantKey: "tenant_rd_platform",
      openId: "ou_feishu_rd_service",
      accessTokenMasked: "u-acc_92fd...k281",
      refreshTokenMasked: "u-rft_2a1e...9b7c",
    },
    logs: [
      {
        id: "log-1",
        time: "2026-04-13 10:24",
        result: "success",
        title: "同步完成",
        description: "新增 18 个文件，更新 41 个文件，删除 2 个文件。",
      },
    ],
  },
  {
    id: "source-local-ops",
    name: "运维共享盘",
    type: "local",
    knowledgeBase: "运维知识库",
    description: "扫描运维 NAS 中 SOP、巡检手册和应急预案",
    target: "/mnt/team-share/ops-docs",
    syncMode: "scheduled",
    scheduleLabel: "每天 02:00 自动同步",
    status: "active",
    connectionState: "connected",
    lastSync: "2026-04-13 08:12",
    nextSync: "下一次计划执行：02:00",
    documentCount: 764,
    addCount: 5,
    deleteCount: 0,
    changeCount: 9,
    permissions: ["读取目录", "读取文件", "下载文件"],
    conflictPolicy: "overwrite",
    enabled: true,
    scopeMode: "all",
    selectedFiles: [],
    fileCandidates: defaultFileCandidates.map((item, index) =>
      index === 1
        ? {
            ...item,
            updateState: "deleted",
          }
        : item,
    ),
    warning: "知识库由后端创建并分配只读权限。",
    oauthConnection: null,
    logs: [
      {
        id: "log-3",
        time: "2026-04-13 08:12",
        result: "success",
        title: "增量扫描完成",
        description: "基于 hash 与 mtime 识别 9 个变更文件。",
      },
    ],
  },
];

function isCloudType(type?: SourceType) {
  return type === "feishu";
}

function getSourceTypeTitle(type: SourceType, t: TFunction) {
  if (type === "local") {
    return t("admin.dataSourceTypeLocal");
  }
  if (type === "feishu") {
    return t("admin.dataSourceTypeFeishu");
  }
  return type;
}

function getSourceTypeDescription(type: SourceType, t: TFunction) {
  if (type === "local") {
    return t("admin.dataSourceTypeLocalDesc");
  }
  if (type === "feishu") {
    return t("admin.dataSourceTypeFeishuDesc");
  }
  return "";
}

function getStatusMeta(status: SourceStatus, t: TFunction) {
  if (status === "active") {
    return { color: "success", text: t("admin.dataSourceStatusActive") as const };
  }
  if (status === "expired") {
    return { color: "warning", text: t("admin.dataSourceStatusExpired") as const };
  }
  if (status === "error") {
    return { color: "error", text: t("admin.dataSourceStatusError") as const };
  }
  return { color: "default", text: t("admin.dataSourceStatusPaused") as const };
}

function getConnectionMeta(state: ConnectionState | OAuthState, t: TFunction) {
  if (state === "connected") {
    return { color: "success", text: t("admin.dataSourceConnectionConnected") };
  }
  if (state === "waiting") {
    return { color: "processing", text: t("admin.dataSourceConnectionWaiting") };
  }
  if (state === "expired") {
    return { color: "warning", text: t("admin.dataSourceConnectionExpired") };
  }
  if (state === "error") {
    return { color: "error", text: t("admin.dataSourceConnectionError") };
  }
  return { color: "default", text: t("admin.dataSourceConnectionPending") };
}

function getConflictPolicyLabel(policy: ConflictPolicy, t: TFunction) {
  if (policy === "overwrite") return t("admin.dataSourceConflictOverwrite");
  if (policy === "skip") return t("admin.dataSourceConflictSkip");
  return t("admin.dataSourceConflictVersioned");
}

function getSyncModeLabel(mode: SyncMode, t: TFunction) {
  if (mode === "manual") return t("admin.dataSourceSyncModeManual");
  return t("admin.dataSourceSyncModeScheduled");
}

function shouldSyncFileCandidate(state: FileUpdateState) {
  return state === "new" || state === "changed" || state === "deleted";
}

function getFileUpdateMeta(state: FileUpdateState, t: TFunction) {
  if (state === "new") {
    return { color: "success", text: t("admin.dataSourceFileUpdateNew") };
  }
  if (state === "changed") {
    return { color: "processing", text: t("admin.dataSourceFileUpdateChanged") };
  }
  if (state === "deleted") {
    return { color: "error", text: t("admin.dataSourceFileUpdateDeleted") };
  }
  return { color: "default", text: t("admin.dataSourceFileUpdateUnchanged") };
}

function getPendingUpdateCount(candidates: FileCandidate[]) {
  return candidates.filter((item) => shouldSyncFileCandidate(item.updateState)).length;
}

function nowString() {
  const current = new Date();
  const pad = (value: number) => `${value}`.padStart(2, "0");
  return `${current.getFullYear()}-${pad(current.getMonth() + 1)}-${pad(
    current.getDate(),
  )} ${pad(current.getHours())}:${pad(current.getMinutes())}`;
}

function loadFeishuAppSetup(): FeishuAppSetup | null {
  try {
    const raw = localStorage.getItem(FEISHU_APP_SETUP_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<FeishuAppSetup>;
    const appId = typeof parsed.appId === "string" ? parsed.appId.trim() : "";
    const appSecret =
      typeof parsed.appSecret === "string" ? parsed.appSecret.trim() : "";
    if (!appId || !appSecret) {
      return null;
    }
    return { appId, appSecret };
  } catch {
    return null;
  }
}

function persistFeishuAppSetup(setup: FeishuAppSetup) {
  localStorage.setItem(FEISHU_APP_SETUP_STORAGE_KEY, JSON.stringify(setup));
}

function clearFeishuAppSetup() {
  localStorage.removeItem(FEISHU_APP_SETUP_STORAGE_KEY);
}

function buildScheduleLabel(values: SourceFormValues, t: TFunction) {
  if (values.syncMode === "manual") {
    return t("admin.dataSourceSyncModeManual");
  }

  const cycleMap: Record<string, string> = {
    daily: t("admin.dataSourceCycleDaily"),
    twoDays: t("admin.dataSourceCycleTwoDays"),
    weekly: t("admin.dataSourceCycleWeekly"),
  };
  const cycleText =
    cycleMap[values.scheduleCycle || "daily"] || t("admin.dataSourceCycleDaily");
  return t("admin.dataSourceScheduleLabel", {
    cycle: cycleText,
    time: values.scheduleTime || "02:00",
  });
}

function buildTarget(values: SourceFormValues, type: SourceType) {
  if (type === "local") {
    return values.path || values.mountName || "-";
  }
  if (type === "s3") {
    return `s3://${values.bucket || ""}/${values.prefix || ""}`.replace(/\/$/, "");
  }
  if (type === "confluence") {
    return values.target || values.spaceKey || "-";
  }
  return values.target || "-";
}

function getNextSyncLabel(values: SourceFormValues, t: TFunction) {
  if (values.syncMode === "manual") {
    return t("admin.dataSourceNextSyncManual");
  }
  return t("admin.dataSourceNextSyncPlanned", {
    time: values.scheduleTime || "02:00",
  });
}

function inferScheduleCycle(scheduleLabel: string) {
  const normalized = scheduleLabel.toLowerCase();
  if (
    scheduleLabel.includes("每 2 天") ||
    normalized.includes("every 2 day") ||
    normalized.includes("2 day")
  ) {
    return "twoDays";
  }
  if (scheduleLabel.includes("每周") || normalized.includes("week")) {
    return "weekly";
  }
  return "daily";
}

function getOAuthStateFromConnection(
  connection?: FeishuDataSourceConnection | null,
): OAuthState {
  if (!connection) {
    return "pending";
  }

  if (connection.status === "connected") {
    return "connected";
  }
  if (connection.status === "expired") {
    return "expired";
  }
  if (connection.status === "error") {
    return "error";
  }

  return "pending";
}

function getSourceStatus(
  enabled: boolean,
  type: SourceType,
  connectionState: ConnectionState,
): SourceStatus {
  if (!enabled) {
    return "paused";
  }

  if (isCloudType(type) && connectionState === "expired") {
    return "expired";
  }
  if (isCloudType(type) && connectionState === "error") {
    return "error";
  }

  return "active";
}

export default function DataSourceManagement() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form] = Form.useForm<SourceFormValues>();
  const [sources, setSources] = useState<DataSourceItem[]>(mockSources);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardMode, setWizardMode] = useState<"create" | "edit">("create");
  const [selectedType, setSelectedType] = useState<SourceType | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [oauthState, setOauthState] = useState<OAuthState>("pending");
  const [connectionVerified, setConnectionVerified] = useState(false);
  const [oauthConnection, setOauthConnection] =
    useState<FeishuDataSourceConnection | null>(null);
  const [feishuAppSetup, setFeishuAppSetup] = useState<FeishuAppSetup | null>(
    () => loadFeishuAppSetup(),
  );
  const [feishuSetupModalOpen, setFeishuSetupModalOpen] = useState(false);
  const [pendingSelectFeishu, setPendingSelectFeishu] = useState(false);
  const [feishuSetupForm] = Form.useForm<FeishuAppSetup>();
  const oauthAttemptRef = useRef<PendingOAuthAttempt | null>(null);

  const syncMode = Form.useWatch("syncMode", form) || "scheduled";
  const isFeishuSetupReady = Boolean(
    feishuAppSetup?.appId.trim() && feishuAppSetup?.appSecret.trim(),
  );

  const detailSource = sources.find((item) => item.id === detailId);
  const totalDocuments = sources.reduce((sum, item) => sum + item.documentCount, 0);
  const activeCount = sources.filter((item) => item.status === "active").length;
  const warningCount = sources.filter((item) =>
    ["expired", "error"].includes(item.status),
  ).length;
  const scheduledCount = sources.filter((item) => item.syncMode === "scheduled").length;

  const clearOauthAttempt = () => {
    if (oauthAttemptRef.current?.timerId) {
      window.clearInterval(oauthAttemptRef.current.timerId);
    }
    oauthAttemptRef.current = null;
  };

  const restorePreviousOauthState = (messageText?: string, level: "warning" | "error" = "warning") => {
    const attempt = oauthAttemptRef.current;
    if (!attempt) {
      if (messageText) {
        message[level](messageText);
      }
      return;
    }

    if (attempt.timerId) {
      window.clearInterval(attempt.timerId);
    }
    setOauthState(attempt.previousState);
    setConnectionVerified(attempt.previousVerified);
    setOauthConnection(attempt.previousConnection);
    oauthAttemptRef.current = null;

    if (messageText) {
      message[level](messageText);
    }
  };

  const applyOauthResult = (payload: FeishuDataSourceOAuthMessage) => {
    const attempt = oauthAttemptRef.current;

    if (payload.channel !== FEISHU_DATA_SOURCE_OAUTH_CHANNEL) {
      return;
    }

    if (attempt?.timerId) {
      window.clearInterval(attempt.timerId);
    }
    if (attempt) {
      attempt.resolved = true;
    }

    if (payload.status === "success") {
      oauthAttemptRef.current = null;
      const nextOauthState = getOAuthStateFromConnection(payload.connection);
      setOauthConnection(payload.connection);
      setOauthState(nextOauthState);
      setConnectionVerified(nextOauthState === "connected");
      message.success(t("admin.dataSourceOauthSuccess"));
      return;
    }

    if (attempt?.previousConnection) {
      restorePreviousOauthState(
        t("admin.dataSourceOauthReconnectFailed", {
          message: payload.message ? ` ${payload.message}` : "",
        }),
        "error",
      );
      return;
    }

    oauthAttemptRef.current = null;
    setOauthConnection(null);
    setOauthState("error");
    setConnectionVerified(false);
    message.error(payload.message || t("admin.dataSourceOauthFailedRetry"));
  };

  useEffect(() => {
    const draft = consumeFeishuDataSourceWizardDraft();
    if (draft) {
      const normalizedWizardStep = Math.min(Math.max(draft.wizardStep, 0), 1);
      setWizardMode(draft.wizardMode);
      setWizardOpen(draft.wizardOpen);
      setWizardStep(normalizedWizardStep);
      setSelectedType((draft.selectedType as SourceType | null) || null);
      setEditingId(draft.editingId);
      setOauthState((draft.oauthState as OAuthState) || "pending");
      setConnectionVerified(Boolean(draft.connectionVerified));
      setOauthConnection(draft.oauthConnection || null);
      window.setTimeout(() => {
        form.setFieldsValue(draft.formValues);
      }, 0);
    }

    const storedResult = consumeFeishuDataSourceOAuthResult();
    if (storedResult) {
      window.setTimeout(() => {
        applyOauthResult(storedResult);
      }, 0);
    }

    const handleMessage = (event: MessageEvent<FeishuDataSourceOAuthMessage>) => {
      if (event.origin !== window.location.origin) {
        return;
      }
      if (!event.data || event.data.channel !== FEISHU_DATA_SOURCE_OAUTH_CHANNEL) {
        return;
      }
      applyOauthResult(event.data);
    };

    window.addEventListener("message", handleMessage);

    return () => {
      window.removeEventListener("message", handleMessage);
      clearOauthAttempt();
    };
  }, [form]);

  const resetWizard = () => {
    form.resetFields();
    setWizardMode("create");
    setWizardStep(0);
    setSelectedType(null);
    setEditingId(null);
    setOauthState("pending");
    setConnectionVerified(false);
    setOauthConnection(null);
  };

  const openCreateWizard = () => {
    resetWizard();
    form.setFieldsValue({
      syncMode: "scheduled",
      scheduleCycle: "daily",
      scheduleTime: "02:00",
      conflictPolicy: "versioned",
    });
    setWizardOpen(true);
  };

  const openEditWizard = (record: DataSourceItem) => {
    resetWizard();
    setWizardMode("edit");
    setWizardOpen(true);
    setWizardStep(1);
    setSelectedType(record.type);
    setEditingId(record.id);
    setOauthConnection(record.oauthConnection || null);
    setOauthState(
      record.oauthConnection
        ? getOAuthStateFromConnection(record.oauthConnection)
        : record.connectionState === "connected"
          ? "connected"
          : record.connectionState === "expired"
            ? "expired"
            : record.connectionState === "error"
              ? "error"
              : "pending",
    );
    setConnectionVerified(record.connectionState === "connected");
    form.setFieldsValue({
      knowledgeBase: record.knowledgeBase,
      syncMode: record.syncMode,
      scheduleCycle:
        inferScheduleCycle(record.scheduleLabel),
      scheduleTime: record.scheduleLabel.match(/\d{2}:\d{2}/)?.[0] || "02:00",
      conflictPolicy: record.conflictPolicy,
      path: record.type === "local" ? record.target : undefined,
      target:
        record.type === "feishu" ||
        record.type === "confluence" ||
        record.type === "notion"
          ? record.target
          : undefined,
      bucket:
        record.type === "s3"
          ? record.target.replace("s3://", "").split("/")[0]
          : undefined,
      prefix:
        record.type === "s3"
          ? record.target.replace(/^s3:\/\/[^/]+\/?/, "")
          : undefined,
      region: record.type === "s3" ? "ap-southeast-1" : undefined,
    });
  };

  const handleCloseWizard = () => {
    setWizardOpen(false);
    resetWizard();
  };

  const applySourceType = (type: SourceType) => {
    setSelectedType(type);
    setConnectionVerified(false);
    setOauthState("pending");
    setOauthConnection(null);
    form.setFieldsValue({
      syncMode: "scheduled",
      scheduleCycle: "daily",
      scheduleTime: "02:00",
      conflictPolicy: "versioned",
      path: "",
      target: "",
    });
  };

  const openFeishuSetupModal = (autoSelect = false) => {
    setPendingSelectFeishu(autoSelect);
    feishuSetupForm.setFieldsValue({
      appId: feishuAppSetup?.appId || "",
      appSecret: feishuAppSetup?.appSecret || "",
    });
    setFeishuSetupModalOpen(true);
  };

  const handleSaveFeishuSetup = async () => {
    const values = await feishuSetupForm.validateFields();
    const nextSetup: FeishuAppSetup = {
      appId: values.appId.trim(),
      appSecret: values.appSecret.trim(),
    };

    persistFeishuAppSetup(nextSetup);
    setFeishuAppSetup(nextSetup);
    setFeishuSetupModalOpen(false);
    message.success(t("admin.dataSourceFeishuCredentialSaved"));

    if (pendingSelectFeishu) {
      applySourceType("feishu");
      setPendingSelectFeishu(false);
    }
  };

  const handleResetFeishuSetup = () => {
    clearOauthAttempt();
    clearFeishuAppSetup();
    setFeishuAppSetup(null);
    setSelectedType((current) => (current === "feishu" ? null : current));
    setOauthState("pending");
    setConnectionVerified(false);
    setOauthConnection(null);
    message.success(t("admin.dataSourceFeishuCredentialReset"));
  };

  const handleSelectType = (type: SourceType) => {
    if (type === "feishu" && !isFeishuSetupReady) {
      openFeishuSetupModal(true);
      return;
    }
    applySourceType(type);
  };

  const handleTestConnection = () => {
    setConnectionVerified(true);
    message.success(t("admin.dataSourceConnectionTestSuccess"));
  };

  const handleConnectAccount = async () => {
    const previousState = oauthState;
    const previousVerified = connectionVerified;
    const previousConnection = oauthConnection;

    try {
      if (!isFeishuSetupReady) {
        message.warning(t("admin.dataSourceFeishuCredentialRequired"));
        return;
      }

      await form.validateFields(["target"]);
      const currentValues = form.getFieldsValue(["target"]);

      setOauthState("waiting");
      const authorizeUrl = await requestFeishuDataSourceAuthorizeUrl({
        scopes: [],
        target: currentValues.target,
        sourceId: editingId,
        reconnect: previousState === "connected",
      });

      const popup = openCenteredPopup(authorizeUrl, t("admin.dataSourceFeishuAuthWindowTitle"));

      oauthAttemptRef.current = {
        timerId: null,
        previousState,
        previousVerified,
        previousConnection,
        resolved: false,
      };

      if (popup) {
        const timerId = window.setInterval(() => {
          if (!popup.closed) {
            return;
          }

          if (oauthAttemptRef.current?.resolved) {
            clearOauthAttempt();
            return;
          }

          restorePreviousOauthState(t("admin.dataSourceOauthWindowClosed"));
        }, 400);

        oauthAttemptRef.current.timerId = timerId;
        popup.focus();
        return;
      }

      const draft: FeishuDataSourceWizardDraft = {
        wizardOpen: true,
        wizardStep,
        wizardMode,
        selectedType,
        editingId,
        oauthState: "waiting",
        connectionVerified: previousVerified,
        oauthConnection: previousConnection,
        formValues: form.getFieldsValue(true),
      };

      saveFeishuDataSourceWizardDraft(draft);
      window.location.assign(authorizeUrl);
    } catch (error: any) {
      setOauthState(previousState);
      setConnectionVerified(previousVerified);
      setOauthConnection(previousConnection);
      message.error(error?.message || t("admin.dataSourceAuthorizeUrlFailed"));
    }
  };

  const openDetailPage = (record: DataSourceItem) => {
    navigate(`/admin/data-sources/${record.id}`, {
      state: {
        source: {
          id: record.id,
          name: record.name,
          target: record.target,
          documentCount: record.documentCount,
          status: record.status,
          lastSync: record.lastSync,
          addCount: record.addCount,
          deleteCount: record.deleteCount,
          changeCount: record.changeCount,
        },
      },
    });
  };

  const validateConnectionBeforeSave = () => {
    if (!selectedType) {
      message.warning(t("admin.dataSourceSelectTypeFirst"));
      return false;
    }

    if (isCloudType(selectedType) && !isFeishuSetupReady) {
      message.warning(t("admin.dataSourceFeishuCredentialFirst"));
      return false;
    }

    if (!connectionVerified) {
      message.warning(t("admin.dataSourceTestConnectionFirst"));
      return false;
    }

    return true;
  };

  const handleNextStep = () => {
    if (wizardStep === 0) {
      if (!selectedType) {
        message.warning(t("admin.dataSourceSelectOneTypeFirst"));
        return;
      }
      setWizardStep(1);
    }
  };

  const handleSave = async () => {
    if (!selectedType) {
      return;
    }

    await form.validateFields();
    if (!validateConnectionBeforeSave()) {
      return;
    }

    const values = form.getFieldsValue();
    const currentTime = nowString();
    const scheduleLabel = buildScheduleLabel(values, t);
    const nextSync = getNextSyncLabel(values, t);
    const connectionState: ConnectionState = connectionVerified
      ? "connected"
      : "pending";
    const creationLog: SyncLogItem = {
      id: `log-${Date.now()}`,
      time: currentTime,
      result: "warning",
      title: t("admin.dataSourceCreatedTitle"),
      description: t("admin.dataSourceCreatedDescription"),
    };
    const nextSource: DataSourceItem = {
      id: editingId || `source-${Date.now()}`,
      name: values.knowledgeBase || getSourceTypeTitle(selectedType, t),
      type: selectedType,
      knowledgeBase: values.knowledgeBase || knowledgeBaseOptions[0],
      description: "",
      target: buildTarget(values, selectedType),
      syncMode: values.syncMode || "scheduled",
      scheduleLabel,
      status: getSourceStatus(true, selectedType, connectionState),
      connectionState,
      lastSync: editingId
        ? sources.find((item) => item.id === editingId)?.lastSync || currentTime
        : t("admin.dataSourceNeverSynced"),
      nextSync,
      documentCount:
        sources.find((item) => item.id === editingId)?.documentCount || 0,
      addCount: sources.find((item) => item.id === editingId)?.addCount || 0,
      deleteCount: sources.find((item) => item.id === editingId)?.deleteCount || 0,
      changeCount:
        sources.find((item) => item.id === editingId)?.changeCount || 0,
      permissions: [t("admin.dataSourcePermissionReadOnly")],
      conflictPolicy: values.conflictPolicy || "versioned",
      enabled: true,
      scopeMode: "all",
      selectedFiles: [],
      fileCandidates: defaultFileCandidates,
      oauthConnection: isCloudType(selectedType) ? oauthConnection : null,
      warning:
        selectedType === "local"
          ? t("admin.dataSourceReadonlyPermissionHint")
          : isCloudType(selectedType)
            ? oauthConnection?.status === "connected"
              ? t("admin.dataSourceOauthConnectedBackendHint")
              : t("admin.dataSourceOauthBackendHint")
            : undefined,
      logs: editingId
        ? sources.find((item) => item.id === editingId)?.logs || []
        : [creationLog],
    };

    setSources((prev) => {
      if (editingId) {
        return prev.map((item) => (item.id === editingId ? nextSource : item));
      }
      return [nextSource, ...prev];
    });

    message.success(
      editingId ? t("admin.dataSourceConfigUpdated") : t("admin.dataSourceCreated"),
    );
    handleCloseWizard();
  };

  const columns: ColumnsType<DataSourceItem> = [
    {
      title: t("admin.dataSourceTableSource"),
      dataIndex: "name",
      key: "name",
      width: 280,
      render: (_value, record) => (
        <div className="data-source-table-name">
          <span className={`data-source-icon data-source-icon-${record.type}`}>
            {sourceTypeOptions.find((item) => item.type === record.type)?.icon}
          </span>
          <div className="data-source-table-copy">
            <Button
              type="link"
              className="data-source-link-button"
              onClick={() => openDetailPage(record)}
            >
              {record.name}
            </Button>
            <Text type="secondary" className="data-source-ellipsis">
              {record.description}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: t("admin.dataSourceTableType"),
      dataIndex: "type",
      key: "type",
      width: 120,
      render: (type: SourceType) => <Tag>{getSourceTypeTitle(type, t)}</Tag>,
    },
    {
      title: t("admin.dataSourceTableKnowledgeBase"),
      dataIndex: "knowledgeBase",
      key: "knowledgeBase",
      width: 140,
    },
    {
      title: t("admin.dataSourceTableSyncStrategy"),
      key: "syncMode",
      width: 260,
      render: (_value, record) => (
        <div className="data-source-sync-cell">
          <Text strong>{getSyncModeLabel(record.syncMode, t)}</Text>
          <Text type="secondary">{record.scheduleLabel}</Text>
        </div>
      ),
    },
    {
      title: t("admin.dataSourceTableConnectionStatus"),
      key: "status",
      width: 140,
      render: (_value, record) => {
        const statusMeta = getStatusMeta(record.status, t);
        const connectionMeta = getConnectionMeta(record.connectionState, t);
        return (
          <Space direction="vertical" size={4}>
            <Tag color={statusMeta.color}>{statusMeta.text}</Tag>
            <Tag color={connectionMeta.color}>{connectionMeta.text}</Tag>
          </Space>
        );
      },
    },
    {
      title: t("admin.dataSourceTableLastSync"),
      key: "lastSync",
      width: 220,
      render: (_value, record) => (
        <div className="data-source-sync-cell">
          <Text>{record.lastSync}</Text>
          <Text type="secondary">{record.nextSync}</Text>
        </div>
      ),
    },
    {
      title: t("admin.dataSourceTableSummary"),
      key: "summary",
      width: 180,
      render: (_value, record) => {
        const pendingCount = getPendingUpdateCount(record.fileCandidates);
        return (
          <div className="data-source-sync-cell">
            <Text>{t("admin.dataSourceSummaryDocs", { count: record.documentCount })}</Text>
            <Text type="secondary">
              {t("admin.dataSourceSummaryChanges", {
                add: record.addCount,
                change: record.changeCount,
                del: record.deleteCount,
              })}
            </Text>
            <Text type={pendingCount > 0 ? "warning" : "secondary"}>
              {t("admin.dataSourceSummaryPending", {
                pending: pendingCount,
                total: record.fileCandidates.length,
              })}
            </Text>
          </div>
        );
      },
    },
    {
      title: t("admin.dataSourceTableActions"),
      key: "actions",
      width: 220,
      fixed: "right",
      render: (_value, record) => (
        <Space wrap>
          <Button type="link" icon={<EyeOutlined />} onClick={() => openDetailPage(record)}>
            {t("admin.dataSourceActionDetail")}
          </Button>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEditWizard(record)}>
            {t("admin.dataSourceActionConfig")}
          </Button>
        </Space>
      ),
    },
  ];

  const renderSummaryCards = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={6}>
        <Card className="data-source-summary-card">
          <Text type="secondary">{t("admin.dataSourceCardTotal")}</Text>
          <div className="data-source-summary-value">{sources.length}</div>
          <Text type="secondary">{t("admin.dataSourceCardTotalHint")}</Text>
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card className="data-source-summary-card">
          <Text type="secondary">{t("admin.dataSourceCardActive")}</Text>
          <div className="data-source-summary-value">{activeCount}</div>
          <Text type="secondary">
            {t("admin.dataSourceCardActiveHint", { count: scheduledCount })}
          </Text>
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card className="data-source-summary-card">
          <Text type="secondary">{t("admin.dataSourceCardDocs")}</Text>
          <div className="data-source-summary-value">{totalDocuments}</div>
          <Text type="secondary">{t("admin.dataSourceCardDocsHint")}</Text>
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card className="data-source-summary-card warning">
          <Text type="secondary">{t("admin.dataSourceCardAlert")}</Text>
          <div className="data-source-summary-value">{warningCount}</div>
          <Text type="secondary">{t("admin.dataSourceCardAlertHint")}</Text>
        </Card>
      </Col>
    </Row>
  );

  const renderSourceTypeStep = () => (
    <div>
      <Paragraph type="secondary" className="data-source-wizard-intro">
        {t("admin.dataSourceTypeStepIntro")}
      </Paragraph>
      <div className="data-source-type-grid">
        {sourceTypeOptions.map((item) => {
          const isFeishuLocked = item.type === "feishu" && !isFeishuSetupReady;
          return (
            <button
              key={item.type}
              type="button"
              className={`data-source-type-card ${
                selectedType === item.type ? "selected" : ""
              } ${isFeishuLocked ? "locked" : ""}`}
              onClick={() => handleSelectType(item.type)}
            >
              <div className="data-source-type-card-header">
                <span className={`data-source-icon data-source-icon-${item.type}`}>
                  {item.icon}
                </span>
                <Space size={6}>
                  {item.type === "feishu" && (
                    isFeishuLocked ? (
                      <span
                        className="data-source-type-gate-icon locked"
                        aria-hidden="true"
                      >
                        <LockOutlined />
                      </span>
                    ) : (
                      <Button
                        type="text"
                        size="small"
                        className="data-source-type-gate-button"
                        icon={<DisconnectOutlined />}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          handleResetFeishuSetup();
                        }}
                      />
                    )
                  )}
                  {item.adminOnly && <Tag color="orange">{t("admin.dataSourceAdminOnly")}</Tag>}
                </Space>
              </div>
              <Text strong>{getSourceTypeTitle(item.type, t)}</Text>
              <Text type="secondary">
                {item.type === "feishu" && isFeishuLocked
                  ? t("admin.dataSourceFeishuLockHint")
                  : getSourceTypeDescription(item.type, t)}
              </Text>
            </button>
          );
        })}
      </div>
    </div>
  );

  const renderConnectionSection = () => {
    if (!selectedType) {
      return null;
    }

    if (isCloudType(selectedType)) {
      const meta = getConnectionMeta(oauthState, t);
      return (
        <Card size="small" className="data-source-connect-card">
          <div className="data-source-connect-header">
            <div>
              <Text strong>{t("admin.dataSourceOauthConnectTitle")}</Text>
              <Paragraph type="secondary">
                {t("admin.dataSourceOauthConnectDesc")}
              </Paragraph>
            </div>
            <Tag color={meta.color}>{meta.text}</Tag>
          </div>
          {!isFeishuSetupReady && (
            <Alert
              showIcon
              type="info"
              message={t("admin.dataSourceFeishuNotReady")}
              description={t("admin.dataSourceFeishuNotReadyDesc")}
            />
          )}
          <Space wrap>
            <Button
              type="primary"
              icon={oauthState === "waiting" ? <SyncOutlined spin /> : <LinkOutlined />}
              loading={oauthState === "waiting"}
              disabled={!isFeishuSetupReady}
              onClick={handleConnectAccount}
            >
              {oauthConnection
                ? t("admin.dataSourceReconnectAccount")
                : t("admin.dataSourceConnectAccount")}
            </Button>
          </Space>
          {oauthConnection && (
            <div className="data-source-oauth-meta">
              <Descriptions
                size="small"
                column={1}
                className="data-source-oauth-descriptions"
              >
                <Descriptions.Item label={t("admin.dataSourceConnectedAccount")}>
                  {oauthConnection.accountName}
                </Descriptions.Item>
                {oauthConnection.tenantKey && (
                  <Descriptions.Item label={t("admin.dataSourceTenantKey")}>
                    {oauthConnection.tenantKey}
                  </Descriptions.Item>
                )}
                {oauthConnection.connectedAt && (
                  <Descriptions.Item label={t("admin.dataSourceConnectedAt")}>
                    {oauthConnection.connectedAt}
                  </Descriptions.Item>
                )}
                {oauthConnection.expiresAt && (
                  <Descriptions.Item label={t("admin.dataSourceAccessTokenExpireAt")}>
                    {oauthConnection.expiresAt}
                  </Descriptions.Item>
                )}
                {oauthConnection.refreshExpiresAt && (
                  <Descriptions.Item label={t("admin.dataSourceRefreshTokenExpireAt")}>
                    {oauthConnection.refreshExpiresAt}
                  </Descriptions.Item>
                )}
                {(oauthConnection.accessTokenMasked ||
                  oauthConnection.refreshTokenMasked) && (
                  <Descriptions.Item label={t("admin.dataSourceTokenSummary")}>
                    <Space direction="vertical" size={2}>
                      {oauthConnection.accessTokenMasked && (
                        <Text code>{oauthConnection.accessTokenMasked}</Text>
                      )}
                      {oauthConnection.refreshTokenMasked && (
                        <Text code>{oauthConnection.refreshTokenMasked}</Text>
                      )}
                    </Space>
                  </Descriptions.Item>
                )}
                {oauthConnection.grantedScopes.length > 0 && (
                  <Descriptions.Item label={t("admin.dataSourceGrantedScopes")}>
                    <Space wrap size={[8, 8]}>
                      {oauthConnection.grantedScopes.map((scope) => (
                        <Tag key={scope}>{scope}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </div>
          )}
          {oauthState === "expired" && (
            <Alert
              showIcon
              type="warning"
              message={t("admin.dataSourceOauthExpired")}
              description={t("admin.dataSourceOauthExpiredDesc")}
            />
          )}
          {oauthState === "error" && (
            <Alert
              showIcon
              type="error"
              message={t("admin.dataSourceOauthError")}
              description={t("admin.dataSourceOauthErrorDesc")}
            />
          )}
        </Card>
      );
    }

    return (
      <Card size="small" className="data-source-connect-card">
          <div className="data-source-connect-header">
            <div>
              <Text strong>{t("admin.dataSourceConnectionTest")}</Text>
              <Paragraph type="secondary">
                {t("admin.dataSourceConnectionTestDesc")}
              </Paragraph>
            </div>
            <Tag color={connectionVerified ? "success" : "default"}>
            {connectionVerified
              ? t("admin.dataSourceConnectionVerified")
              : t("admin.dataSourceConnectionPending")}
            </Tag>
          </div>
          <Button type="primary" icon={<LinkOutlined />} onClick={handleTestConnection}>
          {t("admin.dataSourceConnectionTestAction")}
          </Button>
        </Card>
      );
  };

  const renderConfigStep = () => {
    if (!selectedType) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("admin.dataSourceSelectTypeInPrevStep")}
        />
      );
    }

    return (
      <div className="data-source-wizard-body">
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card className="data-source-form-card" title={t("admin.dataSourceBasicConfig")}>
              <Form.Item
                label={t("admin.dataSourceKnowledgeBaseName")}
                name="knowledgeBase"
                rules={[{ required: true, message: t("admin.dataSourceKnowledgeBaseNameRequired") }]}
              >
                <Input placeholder={t("admin.dataSourceKnowledgeBaseNamePlaceholder")} />
              </Form.Item>
            </Card>

            <Card className="data-source-form-card" title={t("admin.dataSourceAccessConfig")}>
              {selectedType === "local" ? (
                <Form.Item
                  label={t("admin.dataSourceAccessPath")}
                  name="path"
                  rules={[{ required: true, message: t("admin.dataSourceAccessPathRequired") }]}
                >
                  <Input
                    placeholder="/mnt/team-share/ops-docs"
                    onChange={() => setConnectionVerified(false)}
                  />
                </Form.Item>
              ) : (
                <Form.Item
                  label={t("admin.dataSourceFeishuSpace")}
                  name="target"
                  rules={[{ required: true, message: t("admin.dataSourceFeishuSpaceRequired") }]}
                >
                  <Input
                    placeholder="space_rd_platform"
                    onChange={() => setConnectionVerified(false)}
                  />
                </Form.Item>
              )}

              {renderConnectionSection()}
            </Card>

            {renderSyncStrategySection()}
          </Col>
        </Row>
      </div>
    );
  };

  const renderSyncStrategySection = () => (
    <Card className="data-source-form-card" title={t("admin.dataSourceSyncStrategyTitle")}>
      <div className="data-source-strategy-section">
        <Text className="data-source-strategy-label">{t("admin.dataSourceSyncModeTitle")}</Text>
        <Form.Item name="syncMode" className="data-source-strategy-item">
          <Radio.Group className="data-source-sync-mode-pills">
            <Radio.Button value="scheduled">
              <div className="data-source-sync-mode-pill-content">
                <Text strong>{t("admin.dataSourceSyncModeScheduled")}</Text>
                <Text type="secondary">{t("admin.dataSourceSyncModeScheduledDesc")}</Text>
              </div>
            </Radio.Button>
            <Radio.Button value="manual">
              <div className="data-source-sync-mode-pill-content">
                <Text strong>{t("admin.dataSourceSyncModeManual")}</Text>
                <Text type="secondary">{t("admin.dataSourceSyncModeManualDesc")}</Text>
              </div>
            </Radio.Button>
          </Radio.Group>
        </Form.Item>
      </div>

      {syncMode === "scheduled" && (
        <div className="data-source-schedule-panel">
          <div className="data-source-schedule-panel-head">
            <ClockCircleOutlined />
            <Text strong>{t("admin.dataSourceScheduleTitle")}</Text>
            <Text type="secondary">{t("admin.dataSourceScheduleDesc")}</Text>
          </div>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label={t("admin.dataSourceScheduleCycle")} name="scheduleCycle">
                <Select
                  options={[
                    { label: t("admin.dataSourceCycleDaily"), value: "daily" },
                    { label: t("admin.dataSourceCycleTwoDays"), value: "twoDays" },
                    { label: t("admin.dataSourceCycleWeekly"), value: "weekly" },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label={t("admin.dataSourceScheduleTime")} name="scheduleTime">
                <Select
                  options={[
                    { label: "00:00", value: "00:00" },
                    { label: "02:00", value: "02:00" },
                    { label: "06:00", value: "06:00" },
                    { label: "23:00", value: "23:00" },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
        </div>
      )}

    </Card>
  );

  return (
    <div className="admin-page data-source-page">
      <div className="admin-page-toolbar data-source-page-toolbar">
        <div className="admin-page-toolbar-left data-source-page-toolbar-left">
          <div>
            <h2 className="admin-page-title">{t("admin.dataSourceManagement")}</h2>
            <Paragraph className="data-source-page-subtitle">
              {t("admin.dataSourceSubtitle")}
            </Paragraph>
          </div>
          <Badge
            count="UI"
            color="#1677ff"
            className="data-source-page-badge"
            title={t("admin.dataSourceDemoTitle")}
          />
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          className="admin-page-primary-button"
          onClick={openCreateWizard}
        >
          {t("admin.dataSourceCreate")}
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        message={t("admin.dataSourceAccessAlertTitle")}
        description={t("admin.dataSourceAccessAlertDesc")}
      />

      {renderSummaryCards()}

      <Card
        title={t("admin.dataSourceListTitle")}
        extra={
          <Space size="middle">
            <Button
              icon={<ReloadOutlined />}
              onClick={() => message.success(t("admin.dataSourceListRefreshed"))}
            >
              {t("admin.dataSourceRefresh")}
            </Button>
          </Space>
        }
      >
        <Table<DataSourceItem>
          rowKey="id"
          columns={columns}
          dataSource={sources}
          pagination={{ pageSize: 6, showSizeChanger: false }}
          className="admin-page-table data-source-table"
          scroll={{ x: 1480 }}
        />
      </Card>

      <Drawer
        width={560}
        open={Boolean(detailSource)}
        title={detailSource?.name || t("admin.dataSourceDetailTitle")}
        onClose={() => setDetailId(null)}
        extra={
          detailSource ? (
            <Space>
              <Button onClick={() => openEditWizard(detailSource)}>
                {t("admin.dataSourceEditConfig")}
              </Button>
            </Space>
          ) : null
        }
      >
        {detailSource && (
          <div className="data-source-drawer">
            <Space wrap size={[8, 8]}>
              <Tag>{getSourceTypeTitle(detailSource.type, t)}</Tag>
              <Tag color={getStatusMeta(detailSource.status, t).color}>
                {getStatusMeta(detailSource.status, t).text}
              </Tag>
              <Tag color={getConnectionMeta(detailSource.connectionState, t).color}>
                {t("admin.dataSourceConnectionTag", {
                  status: getConnectionMeta(detailSource.connectionState, t).text,
                })}
              </Tag>
            </Space>

            <Paragraph className="data-source-drawer-desc">
              {detailSource.description}
            </Paragraph>

            <Descriptions
              column={1}
              size="small"
              className="data-source-drawer-descriptions"
            >
              <Descriptions.Item label={t("admin.dataSourceTableKnowledgeBase")}>
                {detailSource.knowledgeBase}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourceAccessTarget")}>
                {detailSource.target}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourceSyncModeTitle")}>
                {detailSource.scheduleLabel}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourceTableLastSync")}>
                {detailSource.lastSync}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourceNextRun")}>
                {detailSource.nextSync}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourceConflictPolicy")}>
                {getConflictPolicyLabel(detailSource.conflictPolicy, t)}
              </Descriptions.Item>
              <Descriptions.Item label={t("admin.dataSourcePermissionScope")}>
                <Space wrap>
                  {detailSource.permissions.map((item) => (
                    <Tag key={item}>{item}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              {detailSource.oauthConnection?.accountName && (
                <Descriptions.Item label={t("admin.dataSourceConnectedAccount")}>
                  {detailSource.oauthConnection.accountName}
                </Descriptions.Item>
              )}
              {detailSource.oauthConnection?.connectedAt && (
                <Descriptions.Item label={t("admin.dataSourceConnectedAt")}>
                  {detailSource.oauthConnection.connectedAt}
                </Descriptions.Item>
              )}
              {detailSource.oauthConnection?.expiresAt && (
                <Descriptions.Item label={t("admin.dataSourceTokenExpireAt")}>
                  {detailSource.oauthConnection.expiresAt}
                </Descriptions.Item>
              )}
            </Descriptions>

            {detailSource.warning && (
              <Alert
                showIcon
                type={
                  detailSource.status === "expired" || detailSource.status === "error"
                    ? "warning"
                    : "info"
                }
                message={t("admin.dataSourceNotes")}
                description={detailSource.warning}
              />
            )}

            <Divider orientation="left">{t("admin.dataSourceSyncOverview")}</Divider>
            <Row gutter={[12, 12]}>
              <Col span={8}>
                <Card size="small" className="data-source-mini-card">
                  <Text type="secondary">{t("admin.dataSourceDocTotal")}</Text>
                  <div className="data-source-mini-value">{detailSource.documentCount}</div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" className="data-source-mini-card">
                  <Text type="secondary">{t("admin.dataSourceRecentAdded")}</Text>
                  <div className="data-source-mini-value">{detailSource.addCount}</div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" className="data-source-mini-card">
                  <Text type="secondary">{t("admin.dataSourceRecentChanged")}</Text>
                  <div className="data-source-mini-value">{detailSource.changeCount}</div>
                </Card>
              </Col>
            </Row>

            <Divider orientation="left">{t("admin.dataSourceRecentSyncLogs")}</Divider>
            <Timeline
              items={detailSource.logs.map((log) => ({
                color:
                  log.result === "success"
                    ? "green"
                    : log.result === "warning"
                      ? "orange"
                      : "red",
                dot:
                  log.result === "success" ? (
                    <CheckCircleFilled />
                  ) : log.result === "warning" ? (
                    <ClockCircleOutlined />
                  ) : (
                    <WarningFilled />
                  ),
                children: (
                  <div className="data-source-log-item">
                    <div className="data-source-log-title">{log.title}</div>
                    <div className="data-source-log-time">{log.time}</div>
                    <div className="data-source-log-description">{log.description}</div>
                  </div>
                ),
              }))}
            />

            <Divider orientation="left">{t("admin.dataSourceUpdateQueue")}</Divider>
            <List
              size="small"
              dataSource={detailSource.fileCandidates}
              renderItem={(candidate) => {
                    const updateMeta = getFileUpdateMeta(candidate.updateState, t);
                return (
                  <List.Item>
                    <div className="data-source-selected-file">
                      <Text strong>{candidate.name}</Text>
                      <Text type="secondary">{candidate.path}</Text>
                    </div>
                    <Tag color={updateMeta.color}>{updateMeta.text}</Tag>
                  </List.Item>
                );
              }}
            />

            <Divider orientation="left">{t("admin.dataSourceSyncScope")}</Divider>
            <Text type="secondary">
              {t("admin.dataSourceSyncScopeHint")}
            </Text>
          </div>
        )}
      </Drawer>

      <Modal
        title={t("admin.dataSourceFeishuCredentialModalTitle")}
        open={feishuSetupModalOpen}
        destroyOnHidden
        onCancel={() => {
          setFeishuSetupModalOpen(false);
          setPendingSelectFeishu(false);
        }}
        onOk={handleSaveFeishuSetup}
        okText={
          pendingSelectFeishu
            ? t("admin.dataSourceFeishuCredentialSaveAndSelect")
            : t("common.save")
        }
        cancelText={t("common.cancel")}
      >
        <Form form={feishuSetupForm} layout="vertical">
          <Form.Item
            label={t("admin.dataSourceAppId")}
            name="appId"
            rules={[{ required: true, message: t("admin.dataSourceAppIdRequired") }]}
          >
            <Input placeholder={t("admin.dataSourceAppIdPlaceholder")} />
          </Form.Item>
          <Form.Item
            label={t("admin.dataSourceAppSecret")}
            name="appSecret"
            rules={[{ required: true, message: t("admin.dataSourceAppSecretRequired") }]}
          >
            <Input.Password placeholder={t("admin.dataSourceAppSecretPlaceholder")} />
          </Form.Item>
          <Alert
            showIcon
            type="info"
            message={t("admin.dataSourceFeishuCredentialHint")}
          />
        </Form>
      </Modal>

      <Modal
        title={
          wizardMode === "edit"
            ? t("admin.dataSourceEdit")
            : t("admin.dataSourceCreate")
        }
        open={wizardOpen}
        width={980}
        onCancel={handleCloseWizard}
        destroyOnHidden
        maskClosable={false}
        footer={
          <div className="data-source-wizard-footer">
            <Button onClick={handleCloseWizard}>{t("common.cancel")}</Button>
            <Space>
              {wizardStep > 0 && (
                <Button onClick={() => setWizardStep((step) => step - 1)}>
                  {t("admin.dataSourceWizardPrev")}
                </Button>
              )}
              {wizardStep < 1 && (
                <Button type="primary" onClick={handleNextStep}>
                  {t("admin.dataSourceWizardNext")}
                </Button>
              )}
              {wizardStep === 1 && (
                <Button type="primary" onClick={handleSave}>
                  {t("admin.dataSourceSaveConfig")}
                </Button>
              )}
            </Space>
          </div>
        }
      >
        <Steps
          current={wizardStep}
          items={[
            { title: t("admin.dataSourceWizardType") },
            { title: t("admin.dataSourceWizardConnection") },
          ]}
          className="data-source-wizard-steps"
        />

        <Form form={form} layout="vertical" className="data-source-wizard-form">
          {wizardStep === 0 && renderSourceTypeStep()}
          {wizardStep === 1 && renderConfigStep()}
        </Form>
      </Modal>
    </div>
  );
}
