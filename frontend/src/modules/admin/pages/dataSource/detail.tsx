import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tree,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { DataNode } from "antd/es/tree";
import {
  BookOutlined,
  ArrowLeftOutlined,
  CheckCircleFilled,
  ClockCircleFilled,
  DeleteOutlined,
  ExclamationCircleFilled,
  SearchOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import "./detail.scss";

const { Paragraph, Text, Title } = Typography;

type SourceStatus = "active" | "expired" | "error" | "paused";

interface DataSourceSummary {
  id: string;
  name: string;
  target: string;
  documentCount: number;
  status: SourceStatus;
  lastSync: string;
  addCount: number;
  deleteCount: number;
  changeCount: number;
}

interface DataSourceDetailState {
  source?: DataSourceSummary;
}

interface DocumentStatusRow {
  id: string;
  name: string;
  path: string;
  size: string;
  tags: string[];
  updateState: "new" | "changed" | "unchanged" | "deleted";
  syncDetail: string;
  parseStatus: "parsed" | "reindexing" | "duplicate" | "deleted" | "failed";
  sourceUpdatedAt: string;
  updatedAt: string;
}

type SyncStatusFilter = "updated" | "unchanged";

const fallbackSources: Record<
  string,
  DataSourceSummary & { storageUsed: string }
> = {
  "source-feishu-rd": {
    id: "source-feishu-rd",
    name: "飞书研发知识库",
    target: "Wiki://space_rd_platform",
    documentCount: 1284,
    status: "active",
    lastSync: "2026-04-13 10:24",
    addCount: 18,
    deleteCount: 2,
    changeCount: 41,
    storageUsed: "452.8 MB",
  },
  "source-local-ops": {
    id: "source-local-ops",
    name: "运维共享盘",
    target: "/mnt/team-share/ops-docs",
    documentCount: 764,
    status: "active",
    lastSync: "2026-04-13 08:12",
    addCount: 5,
    deleteCount: 0,
    changeCount: 9,
    storageUsed: "218.6 MB",
  },
};

const documentStatusMap: Record<
  string,
  {
    storageUsed: string;
    documents: DocumentStatusRow[];
  }
> = {
  "source-feishu-rd": {
    storageUsed: "452.8 MB",
    documents: [
      {
        id: "fs-1",
        name: "飞书接入开发文档.pdf",
        path: "/接入文档/飞书接入开发文档.pdf",
        size: "1.4 MB",
        tags: ["接入", "飞书"],
        updateState: "changed",
        syncDetail: "内容变更，已完成增量重解析",
        parseStatus: "parsed",
        sourceUpdatedAt: "2026-04-13 10:21",
        updatedAt: "2026-04-13 10:24",
      },
      {
        id: "fs-2",
        name: "OAuth 接口定义说明.docx",
        path: "/接入文档/OAuth 接口定义说明.docx",
        size: "856 KB",
        tags: ["OAuth", "接口"],
        updateState: "new",
        syncDetail: "新文档入库，已生成向量索引",
        parseStatus: "parsed",
        sourceUpdatedAt: "2026-04-13 09:52",
        updatedAt: "2026-04-13 09:58",
      },
      {
        id: "fs-3",
        name: "知识库权限申请流程.md",
        path: "/权限中心/知识库权限申请流程.md",
        size: "122 KB",
        tags: ["权限"],
        updateState: "changed",
        syncDetail: "权限范围更新，等待重建索引",
        parseStatus: "reindexing",
        sourceUpdatedAt: "2026-04-13 09:40",
        updatedAt: "2026-04-13 09:41",
      },
      {
        id: "fs-4",
        name: "旧版连接说明.docx",
        path: "/历史归档/旧版连接说明.docx",
        size: "730 KB",
        tags: ["归档"],
        updateState: "unchanged",
        syncDetail: "检测到重复文档，按多版本策略保留历史版本",
        parseStatus: "duplicate",
        sourceUpdatedAt: "2026-04-11 23:55",
        updatedAt: "2026-04-12 02:01",
      },
    ],
  },
  "source-local-ops": {
    storageUsed: "218.6 MB",
    documents: [
      {
        id: "ops-1",
        name: "巡检标准作业手册.pdf",
        path: "/mnt/team-share/ops-docs/巡检标准作业手册.pdf",
        size: "2.1 MB",
        tags: ["巡检", "SOP"],
        updateState: "changed",
        syncDetail: "内容变更，已完成增量重解析",
        parseStatus: "parsed",
        sourceUpdatedAt: "2026-04-13 08:09",
        updatedAt: "2026-04-13 08:12",
      },
      {
        id: "ops-2",
        name: "应急值班排班.xlsx",
        path: "/mnt/team-share/ops-docs/应急值班排班.xlsx",
        size: "414 KB",
        tags: ["排班"],
        updateState: "new",
        syncDetail: "新文档入库，已完成索引生成",
        parseStatus: "parsed",
        sourceUpdatedAt: "2026-04-13 08:00",
        updatedAt: "2026-04-13 08:05",
      },
      {
        id: "ops-3",
        name: "故障复盘记录.md",
        path: "/mnt/team-share/ops-docs/故障复盘记录.md",
        size: "96 KB",
        tags: ["复盘"],
        updateState: "changed",
        syncDetail: "检测到内容变更，正在重新切分 chunk",
        parseStatus: "reindexing",
        sourceUpdatedAt: "2026-04-13 07:53",
        updatedAt: "2026-04-13 07:58",
      },
      {
        id: "ops-4",
        name: "历史拓扑图.pptx",
        path: "/mnt/team-share/ops-docs/历史拓扑图.pptx",
        size: "8.2 MB",
        tags: ["拓扑", "历史"],
        updateState: "deleted",
        syncDetail: "文件已从源目录删除，等待清理索引",
        parseStatus: "deleted",
        sourceUpdatedAt: "2026-04-12 21:10",
        updatedAt: "2026-04-12 21:16",
      },
    ],
  },
};

function getStatusMeta(status: SourceStatus, t: TFunction) {
  if (status === "active") {
    return { color: "success", text: t("admin.dataSourceStatusActive") };
  }
  if (status === "expired") {
    return { color: "warning", text: t("admin.dataSourceStatusExpired") };
  }
  if (status === "error") {
    return { color: "error", text: t("admin.dataSourceStatusError") };
  }
  return { color: "default", text: t("admin.dataSourceStatusPaused") };
}

function getParseStatusMeta(status: DocumentStatusRow["parseStatus"], t: TFunction) {
  if (status === "parsed") {
    return {
      color: "#12b76a",
      text: t("admin.dataSourceParseParsed"),
      icon: <CheckCircleFilled />,
    };
  }
  if (status === "reindexing") {
    return {
      color: "#1677ff",
      text: t("admin.dataSourceParseReindexing"),
      icon: <SyncOutlined spin />,
    };
  }
  if (status === "duplicate") {
    return {
      color: "#f79009",
      text: t("admin.dataSourceParseDuplicate"),
      icon: <ClockCircleFilled />,
    };
  }
  if (status === "deleted") {
    return {
      color: "#f04438",
      text: t("admin.dataSourceParseDeleted"),
      icon: <DeleteOutlined />,
    };
  }
  return {
    color: "#f04438",
    text: t("admin.dataSourceParseFailed"),
    icon: <ExclamationCircleFilled />,
  };
}

function getUpdateStateMeta(status: DocumentStatusRow["updateState"], t: TFunction) {
  if (status === "new") {
    return {
      text: t("admin.dataSourceFileUpdateNew"),
      detail: t("admin.dataSourceFileUpdateNewDetail"),
      tone: "new" as const,
    };
  }
  if (status === "changed") {
    return {
      text: t("admin.dataSourceFileUpdateChangedDetailTitle"),
      detail: t("admin.dataSourceFileUpdateChangedDetail"),
      tone: "changed" as const,
    };
  }
  if (status === "deleted") {
    return {
      text: t("admin.dataSourceFileUpdateDeletedDetailTitle"),
      detail: t("admin.dataSourceFileUpdateDeletedDetail"),
      tone: "deleted" as const,
    };
  }
  return {
    text: t("admin.dataSourceFileUpdateUnchanged"),
    detail: t("admin.dataSourceFileUpdateUnchangedDetail"),
    tone: "unchanged" as const,
  };
}

function isDocumentNeedSync(status: DocumentStatusRow["updateState"]) {
  return status === "new" || status === "changed" || status === "deleted";
}

function matchSyncStatus(
  status: DocumentStatusRow["updateState"],
  filter: SyncStatusFilter,
) {
  if (filter === "updated") {
    return isDocumentNeedSync(status);
  }
  return status === "unchanged";
}

function formatNow() {
  const current = new Date();
  const pad = (value: number) => `${value}`.padStart(2, "0");
  return `${current.getFullYear()}-${pad(current.getMonth() + 1)}-${pad(
    current.getDate(),
  )} ${pad(current.getHours())}:${pad(current.getMinutes())}`;
}

function getDirectoryLabel(path: string, sourceName: string) {
  const segments = path.split("/").filter(Boolean);
  if (segments.length <= 1) {
    return sourceName;
  }
  return segments.length > 2 ? segments[segments.length - 2] : segments[0];
}

function getDocumentType(name: string) {
  const [, extension = "unknown"] = name.split(/\.(?=[^.]+$)/);
  return extension.toLowerCase();
}

export default function DataSourceDetail() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id = "" } = useParams();
  const location = useLocation();
  const [keyword, setKeyword] = useState("");

  const routeState = location.state as DataSourceDetailState | null;
  const routeSource = routeState?.source;
  const fallbackSource = fallbackSources[id];
  const detailSource = routeSource
    ? {
        ...routeSource,
        storageUsed:
          documentStatusMap[routeSource.id]?.storageUsed ||
          fallbackSource?.storageUsed ||
          "0 MB",
      }
    : fallbackSource;

  const documentsSeed =
    (detailSource && documentStatusMap[detailSource.id]?.documents) || [];
  const [documents, setDocuments] = useState<DocumentStatusRow[]>(documentsSeed);
  const [syncSelectedDocIds, setSyncSelectedDocIds] = useState<string[]>([]);
  const [syncPickerOpen, setSyncPickerOpen] = useState(false);
  const [syncKeyword, setSyncKeyword] = useState("");
  const [syncStatusFilter, setSyncStatusFilter] =
    useState<SyncStatusFilter>("updated");
  const [lastSync, setLastSync] = useState(
    detailSource?.lastSync || t("admin.dataSourceNeverSynced"),
  );
  const [lastOperation, setLastOperation] = useState<{
    syncedCount: number;
    ignoredCount: number;
    checkedCount: number;
    time: string;
  } | null>(null);

  useEffect(() => {
    setDocuments(documentsSeed);
    setSyncSelectedDocIds([]);
    setSyncPickerOpen(false);
  }, [documentsSeed]);

  useEffect(() => {
    setLastSync(detailSource?.lastSync || t("admin.dataSourceNeverSynced"));
  }, [detailSource?.lastSync, t]);

  const filteredDocuments = useMemo(() => {
    const normalized = keyword.trim().toLowerCase();
    if (!normalized) {
      return documents;
    }

    return documents.filter(
      (item) =>
        item.name.toLowerCase().includes(normalized) ||
        item.path.toLowerCase().includes(normalized) ||
        item.syncDetail.toLowerCase().includes(normalized),
    );
  }, [documents, keyword]);

  const pendingDocumentsCount = documents.filter((item) =>
    isDocumentNeedSync(item.updateState),
  ).length;
  const newDocumentsCount = documents.filter((item) => item.updateState === "new").length;
  const changedDocumentsCount = documents.filter(
    (item) => item.updateState === "changed",
  ).length;
  const deletedDocumentsCount = documents.filter(
    (item) => item.updateState === "deleted",
  ).length;
  const sourceNameForPath = detailSource?.name || t("admin.dataSourceFallbackName");

  const openSyncPicker = () => {
    setSyncKeyword("");
    setSyncStatusFilter("updated");
    setSyncSelectedDocIds(
      documents
        .filter((item) => isDocumentNeedSync(item.updateState))
        .map((item) => item.id),
    );
    setSyncPickerOpen(true);
  };

  const runSyncPipeline = (targetDocumentIds: string[]) => {
    if (targetDocumentIds.length === 0) {
      message.warning(t("admin.dataSourceDetailSelectFileFirst"));
      return false;
    }

    const targetSet = new Set(targetDocumentIds);
    const currentTime = formatNow();
    const checkedRows = documents.filter((item) => targetSet.has(item.id));
    const syncRows = checkedRows.filter((item) => isDocumentNeedSync(item.updateState));
    const checkedCount = checkedRows.length;
    const syncedCount = syncRows.length;
    const ignoredCount = checkedCount - syncedCount;

    if (syncedCount === 0) {
      message.info(
        t("admin.dataSourceDetailSyncNoChange", { checkedCount }),
      );
      setLastOperation({
        syncedCount,
        ignoredCount,
        checkedCount,
        time: currentTime,
      });
      return true;
    }

    setDocuments((prev) =>
      prev
        .map((item) => {
          if (!targetSet.has(item.id) || !isDocumentNeedSync(item.updateState)) {
            return item;
          }

          if (item.updateState === "deleted") {
            return null;
          }

          return {
            ...item,
            updateState: "unchanged",
            parseStatus: "parsed",
            syncDetail: t("admin.dataSourceDetailManualSyncDone"),
            updatedAt: currentTime,
          };
        })
        .filter(Boolean) as DocumentStatusRow[],
    );

    setLastSync(currentTime);
    setLastOperation({
      syncedCount,
      ignoredCount,
      checkedCount,
      time: currentTime,
    });
    message.success(
      t("admin.dataSourceDetailSyncDone", {
        syncedCount,
        ignoredCount,
      }),
    );
    setSyncSelectedDocIds([]);
    return true;
  };

  const filteredSyncDocuments = useMemo(() => {
    const normalizedKeyword = syncKeyword.trim().toLowerCase();
    return documents.filter((item) => {
      const keywordMatched =
        !normalizedKeyword ||
        item.name.toLowerCase().includes(normalizedKeyword) ||
        item.path.toLowerCase().includes(normalizedKeyword);
      return keywordMatched && matchSyncStatus(item.updateState, syncStatusFilter);
    });
  }, [documents, syncKeyword, syncStatusFilter]);

  const syncTreeData = useMemo<DataNode[]>(() => {
    if (filteredSyncDocuments.length === 0) {
      return [];
    }

    type MutableNode = {
      key: string;
      title: ReactNode;
      children: Map<string, MutableNode>;
    };

    const createDirNode = (key: string, title: string): MutableNode => ({
      key,
      title: <span>{title}</span>,
      children: new Map<string, MutableNode>(),
    });

    const root = createDirNode("root", "root");

    filteredSyncDocuments.forEach((item) => {
      const segments = item.path.split("/").filter(Boolean);
      const folderSegments = segments.slice(0, -1);
      let currentNode = root;
      let currentPath = "";

      folderSegments.forEach((segment) => {
        currentPath = `${currentPath}/${segment}`;
        const key = `dir:${currentPath}`;
        if (!currentNode.children.has(key)) {
          currentNode.children.set(key, createDirNode(key, segment));
        }
        currentNode = currentNode.children.get(key)!;
      });

      const meta = getUpdateStateMeta(item.updateState, t);
      const leafKey = `file:${item.id}`;
      currentNode.children.set(leafKey, {
        key: leafKey,
        title: (
          <div className="data-source-sync-tree-file">
            <div className="data-source-sync-tree-file-main">
              <span>{item.name}</span>
              {isDocumentNeedSync(item.updateState) && (
                <span
                  className={`data-source-sync-tree-chip data-source-sync-tree-chip-${meta.tone}`}
                >
                  {meta.text}
                </span>
              )}
            </div>
          </div>
        ),
        children: new Map<string, MutableNode>(),
      });
    });

    const toTreeData = (node: MutableNode): DataNode[] =>
      Array.from(node.children.values()).map((child) => {
        const children = toTreeData(child);
        return {
          key: child.key,
          title: child.title,
          children: children.length > 0 ? children : undefined,
          isLeaf: children.length === 0,
        };
      });

    return toTreeData(root);
  }, [filteredSyncDocuments, t]);

  const checkedTreeKeys = syncSelectedDocIds.map((id) => `file:${id}`);
  const filteredSyncDocIds = filteredSyncDocuments.map((item) => item.id);
  const hasFilteredSelected = filteredSyncDocIds.some((id) =>
    syncSelectedDocIds.includes(id),
  );

  const columns: ColumnsType<DocumentStatusRow> = [
    {
      title: t("admin.dataSourceDetailTableDocName"),
      dataIndex: "name",
      key: "name",
      width: 360,
      render: (_value, record) => (
        <div className="data-source-detail-doc">
          <div className="data-source-detail-doc-name">
            <BookOutlined />
            <span>{record.name}</span>
          </div>
          <div className="data-source-detail-doc-path">{record.path}</div>
        </div>
      ),
    },
    {
      title: t("admin.dataSourceDetailTableTags"),
      dataIndex: "tags",
      key: "tags",
      width: 160,
      render: (tags: string[]) =>
        tags.length ? (
          <div className="data-source-detail-tags">
            {tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        ) : (
          "-"
        ),
    },
    {
      title: t("admin.dataSourceDetailTableDirectory"),
      dataIndex: "path",
      key: "path",
      width: 160,
      render: (path: string) => getDirectoryLabel(path, sourceNameForPath),
    },
    {
      title: t("admin.dataSourceDetailTableUpdateState"),
      dataIndex: "updateState",
      key: "updateState",
      width: 220,
      render: (updateState: DocumentStatusRow["updateState"]) => {
        const meta = getUpdateStateMeta(updateState, t);
        return (
          <div className="data-source-detail-update-state">
            <span className={`data-source-update-chip data-source-update-chip-${meta.tone}`}>
              <span className="data-source-update-chip-dot" />
              {meta.text}
            </span>
            <Text type="secondary">{meta.detail}</Text>
          </div>
        );
      },
    },
    {
      title: t("admin.dataSourceDetailTableParseStatus"),
      dataIndex: "parseStatus",
      key: "parseStatus",
      width: 140,
      render: (parseStatus: DocumentStatusRow["parseStatus"], record) => {
        const meta = getParseStatusMeta(parseStatus, t);
        return (
          <Tag
            color={
              parseStatus === "parsed"
                ? "success"
                : parseStatus === "reindexing"
                  ? "processing"
                  : parseStatus === "duplicate"
                    ? "warning"
                    : "error"
            }
            title={record.syncDetail}
          >
            {meta.text}
          </Tag>
        );
      },
    },
    {
      title: t("admin.dataSourceDetailTableDocType"),
      dataIndex: "name",
      key: "docType",
      width: 120,
      render: (name: string) => getDocumentType(name),
    },
    {
      title: t("admin.dataSourceDetailTableSize"),
      dataIndex: "size",
      key: "size",
      width: 120,
      render: (size: string) => (
        <Text className="data-source-detail-size" type="secondary">
          {size}
        </Text>
      ),
    },
    {
      title: t("admin.dataSourceDetailTableSourceUpdatedAt"),
      dataIndex: "sourceUpdatedAt",
      key: "sourceUpdatedAt",
      width: 180,
    },
    {
      title: t("admin.dataSourceDetailTableUpdatedAt"),
      dataIndex: "updatedAt",
      key: "updatedAt",
      width: 180,
    },
  ];

  if (!detailSource) {
    return (
      <div className="admin-page data-source-detail-page">
        <Button
          type="link"
          icon={<ArrowLeftOutlined />}
          className="data-source-detail-back"
          onClick={() => navigate("/admin/data-sources")}
        >
          {t("admin.dataSourceBackToList")}
        </Button>
        <Card>
          <Empty description={t("admin.dataSourceDetailNotFound")} />
        </Card>
      </div>
    );
  }

  const statusMeta = getStatusMeta(detailSource.status, t);

  return (
    <div className="admin-page data-source-detail-page">
      <Button
        type="link"
        icon={<ArrowLeftOutlined />}
        className="data-source-detail-back"
        onClick={() => navigate("/admin/data-sources")}
      >
        {t("admin.dataSourceBackToList")}
      </Button>

      <div className="data-source-detail-header">
        <Space align="center" size={16} wrap>
          <Title level={2} className="data-source-detail-title">
            {detailSource.name}
          </Title>
          <Tag color={statusMeta.color} className="data-source-detail-title-tag">
            {statusMeta.text}
          </Tag>
        </Space>
        <Paragraph className="data-source-detail-description">
          {t("admin.dataSourceDetailLastSync", { time: lastSync })}
        </Paragraph>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card className="data-source-detail-stat-card">
            <Text className="data-source-detail-stat-label">
              {t("admin.dataSourceDetailSyncPath")}
            </Text>
            <div className="data-source-detail-stat-value path">
              {detailSource.target}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="data-source-detail-stat-card">
            <Text className="data-source-detail-stat-label">
              {t("admin.dataSourceDetailParsedDocs")}
            </Text>
            <div className="data-source-detail-stat-value">
              {documents.length}
              <span>{t("admin.dataSourceDetailFileUnit")}</span>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="data-source-detail-stat-card">
            <Text className="data-source-detail-stat-label">
              {t("admin.dataSourceDetailStorageUsed")}
            </Text>
            <div className="data-source-detail-stat-value">
              {detailSource.storageUsed}
            </div>
          </Card>
        </Col>
      </Row>

      <Card
        className="data-source-detail-change-card"
        bodyStyle={{ paddingBottom: 12 }}
      >
        <Space wrap size={[12, 12]}>
          <Tag color="green">{t("admin.dataSourceDetailTagNew", { count: newDocumentsCount })}</Tag>
          <Tag color="blue">
            {t("admin.dataSourceDetailTagChanged", { count: changedDocumentsCount })}
          </Tag>
          <Tag color="red">
            {t("admin.dataSourceDetailTagDeleted", { count: deletedDocumentsCount })}
          </Tag>
          <Tag color={pendingDocumentsCount > 0 ? "warning" : "default"}>
            {t("admin.dataSourceDetailTagPending", { count: pendingDocumentsCount })}
          </Tag>
          <Tag>{t("admin.dataSourceDetailTagTotal", { count: documents.length })}</Tag>
        </Space>
      </Card>

      <Alert
        showIcon
        type="info"
        message={t("admin.dataSourceDetailExecutionTitle")}
        description={t("admin.dataSourceDetailExecutionDesc")}
      />

      {lastOperation && (
        <Alert
          showIcon
          type={lastOperation.syncedCount > 0 ? "success" : "warning"}
          message={t("admin.dataSourceDetailLastManualPull")}
          description={t("admin.dataSourceDetailLastManualPullDesc", {
            time: lastOperation.time,
            checked: lastOperation.checkedCount,
            synced: lastOperation.syncedCount,
            ignored: lastOperation.ignoredCount,
          })}
        />
      )}

      <Card
        title={t("admin.dataSourceDetailDocChangeTitle")}
        extra={
          <Space wrap>
            <Button
              type="primary"
              onClick={openSyncPicker}
            >
              {t("admin.dataSourceDetailSyncNow")}
            </Button>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder={t("admin.dataSourceDetailSearchDocPlaceholder")}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              className="data-source-detail-search"
            />
          </Space>
        }
      >
        <Table<DocumentStatusRow>
          rowKey="id"
          columns={columns}
          dataSource={filteredDocuments}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          className="admin-page-table data-source-detail-table"
          locale={{ emptyText: t("admin.dataSourceDetailNoDocStatus") }}
          scroll={{ x: 1520 }}
        />
      </Card>

      <Modal
        title={t("admin.dataSourceDetailManualPullTitle")}
        open={syncPickerOpen}
        onCancel={() => setSyncPickerOpen(false)}
        okText={t("admin.dataSourceDetailStartPull", { count: syncSelectedDocIds.length })}
        okButtonProps={{ disabled: syncSelectedDocIds.length === 0 }}
        onOk={() => {
          const finished = runSyncPipeline(syncSelectedDocIds);
          if (finished) {
            setSyncPickerOpen(false);
          }
        }}
        width={860}
        destroyOnClose
      >
        <div className="data-source-sync-picker">
          <Space wrap className="data-source-sync-picker-filters">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder={t("admin.dataSourceDetailSearchInModalPlaceholder")}
              value={syncKeyword}
              onChange={(event) => setSyncKeyword(event.target.value)}
              className="data-source-sync-picker-keyword"
            />
            <Space wrap className="data-source-sync-picker-actions">
              <Select<SyncStatusFilter>
                value={syncStatusFilter}
                className="data-source-sync-picker-status"
                onChange={setSyncStatusFilter}
                options={[
                  { label: t("admin.dataSourceDetailFilterUpdated"), value: "updated" },
                  { label: t("admin.dataSourceDetailFilterUnchanged"), value: "unchanged" },
                ]}
              />
              {hasFilteredSelected ? (
                <Button
                  onClick={() =>
                    setSyncSelectedDocIds((prev) =>
                      prev.filter((id) => !filteredSyncDocIds.includes(id)),
                    )
                  }
                  disabled={filteredSyncDocIds.length === 0}
                >
                  {t("chat.cancelSelectAll")}
                </Button>
              ) : (
                <Button
                  onClick={() => setSyncSelectedDocIds(filteredSyncDocIds)}
                  disabled={filteredSyncDocIds.length === 0}
                >
                  {t("chat.selectAll")}
                </Button>
              )}
            </Space>
          </Space>

          <Alert
            showIcon
            type="info"
            message={t("admin.dataSourceDetailTreeSelectTitle")}
            description={t("admin.dataSourceDetailTreeSelectDesc")}
          />

          {syncTreeData.length > 0 ? (
            <Tree
              checkable
              defaultExpandAll
              checkedKeys={checkedTreeKeys}
              treeData={syncTreeData}
              className="data-source-sync-tree"
              onCheck={(keys) => {
                const nextKeys = Array.isArray(keys) ? keys : keys.checked;
                const fileIds = nextKeys
                  .map((key) => `${key}`)
                  .filter((key) => key.startsWith("file:"))
                  .map((key) => key.slice("file:".length));
                setSyncSelectedDocIds(fileIds);
              }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("admin.dataSourceDetailNoMatchedFile")}
            />
          )}
        </div>
      </Modal>
    </div>
  );
}
