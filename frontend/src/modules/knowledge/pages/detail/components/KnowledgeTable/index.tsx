import {
  useEffect,
  useRef,
  useState,
  useImperativeHandle,
  forwardRef,
} from "react";
import {
  Dataset,
  Doc,
  DocDataSourceTypeEnum,
  DocDocumentStageEnum,
  DocTypeEnum,
  JobJobTypeEnum,
} from "@/api/generated/knowledge-client";
import {
  DocumentServiceApi,
  JobServiceApi,
} from "@/modules/knowledge/utils/request";
import {
  Button,
  Checkbox,
  message,
  Modal,
  Dropdown,
  Tooltip,
  TablePaginationConfig,
  Tag,
} from "antd";
import type { MenuProps } from "antd";
import moment from "moment";
import {
  FOLDER_NAME_REG,
  TIME_FORMAT,
} from "@/modules/knowledge/constants/common";
import {
  BookOutlined,
  FolderOutlined,
  FolderOpenOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  DownOutlined,
  EditFilled,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { cloneDeep } from "lodash";
import { ColumnType } from "antd/es/table";
import FileUtils from "@/modules/knowledge/utils/file";
import RenameModel, {
  RenameFormItem,
  RenameModalRef,
} from "@/modules/knowledge/components/RenameModel";
import RestartKnowledgeModal, {
  type IRestartKnowledgeProps,
} from "../RestartKnowledgeModal";
import TreeUtils from "@/modules/knowledge/utils/tree";
import UIUtils from "@/modules/knowledge/utils/ui";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";
import type { Job } from "@/api/generated/knowledge-client";

import { ListPageTable } from "@/components/ui";
import CopyMoveModal from "../CopyMoveModal";
import EditTags from "./editTags";
import BatchEditTags from "../batchEditTags";
import BatchMoveModal from "../batchMoveModal";

// 扩展 Doc 类型以支持树形结构
export interface TreeNode extends Doc {
  key: string;
  title: string;
  children?: TreeNode[];
  isLeaf?: boolean;
  level: number;
  loaded?: boolean;
  document_id?: string;
  document_stage: DocDocumentStageEnum;
}

export interface IKnowledgeListRef {
  getTableData: (params?: {
    pId: string;
    level: number;
    parentNode?: TreeNode;
  }) => void;
  updateDocument: (params?: {
    documentId: string;
    level?: number;
    parentNode?: TreeNode;
  }) => void;
  treeData: TreeNode[];
  deleteKnowledge: () => void;
  downloadCheckedKnowledge: () => void;
  restartCheckedKnowledge: () => void;
  openBatchEditTags: () => void;
  openBatchMove: () => void;
  refresh: (keyword: string) => void;
}

export interface BatchMoveDocument {
  documentId: string;
  parentId: string;
  dataSourceType: string;
}

interface Props {
  detail: Dataset;
  onImportKnowledge: (data: { p_id?: string; targetPath?: string }) => void;
  getImportingTotal: () => void;
  getDetail: () => void;
}

const DocumentStageEnum = {
  [DocDocumentStageEnum.DocumentUploaded]: "未解析",
  [DocDocumentStageEnum.DocumentParsing]: "解析中",
  [DocDocumentStageEnum.DocumentParseSuccessfully]: "已解析",
  [DocDocumentStageEnum.DocumentParsingFailed]: "解析失败",
  [DocDocumentStageEnum.DocumentParsingCancelled]: "解析取消",
  [DocDocumentStageEnum.DocumentQueued]: "排队中",
  [DocDocumentStageEnum.DocumentCrawling]: "爬取中",
  [DocDocumentStageEnum.DocumentCrawlingFailed]: "爬取失败",
  [DocDocumentStageEnum.DocumentFailed]: "失败",
  [DocDocumentStageEnum.DocumentCrawlingQueued]: "爬取排队",
};

const KnowledgeTable = forwardRef<IKnowledgeListRef, Props>((props, ref) => {
  const { detail, onImportKnowledge, getDetail, getImportingTotal } = props;
  const navigate = useNavigate();
  const [tableData, setTableData] = useState<TreeNode[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [currentNode, setCurrentNode] = useState<TreeNode | null>(null);
  const knowledgeRenameRef = useRef<RenameModalRef>(null);
  const restartKnowledgeRef = useRef<IRestartKnowledgeProps>(null);
  const [keyword, setKeyword] = useState("");
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const [showCopyModal, setShowCopyModal] = useState(false);
  const [currentDocInfo, setCurrentDocInfo] = useState({});
  const [action, setAction] = useState<"copy" | "move">("copy");
  const [showTagEditModal, setShowTagEditModal] = useState(false);
  const [tagEditRecord, setTagEditRecord] = useState<TreeNode | null>(null);

  // 批量标签编辑状态管理
  const [batchTagEditState, setBatchTagEditState] = useState({
    showModal: false,
    documentIds: [] as string[],
    folderIds: [] as string[],
    selectedFileCount: 0,
  });
  const [batchMoveState, setBatchMoveState] = useState({
    showModal: false,
    documents: [] as BatchMoveDocument[],
    selectedFileCount: 0,
  });

  // 使用权限 store
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );
  const hasOnlyReadPermission = useDatasetPermissionStore((state) =>
    state.hasOnlyReadPermission(),
  );
  const hasUploadPermission = useDatasetPermissionStore((state) =>
    state.hasUploadPermission(),
  );

  // 递归获取所有子节点的 key
  const getAllChildrenKeys = (node: TreeNode): string[] => {
    const keys: string[] = [];
    if (node.children) {
      node.children.forEach((child) => {
        if (child.document_id) {
          keys.push(child.document_id);
          keys.push(...getAllChildrenKeys(child));
        }
      });
    }
    return keys;
  };

  /** 文件夹是否全选：有子项时看子项是否全选，无子项时看自身是否选中 */
  const isFolderFullySelected = (node: TreeNode): boolean => {
    const childKeys = getAllChildrenKeys(node);
    if (childKeys.length === 0) {
      return selectedRowKeys.includes(node.document_id || "");
    }
    return childKeys.every((k) => selectedRowKeys.includes(k));
  };

  // 获取所有数据的 key
  const getAllKeys = (data: TreeNode[]): string[] => {
    const keys: string[] = [];
    data.forEach((item) => {
      if (item.document_id) {
        keys.push(item.document_id);
        keys.push(...getAllChildrenKeys(item));
      }
    });
    return keys;
  };

  // 处理全选/取消全选
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedRowKeys(getAllKeys(tableData));
    } else {
      setSelectedRowKeys([]);
    }
  };

  // 处理单个选择
  const handleSelect = (record: TreeNode, selected: boolean) => {
    if (!record.document_id) return;

    let keys = [...selectedRowKeys];
    const selfAndChildren = [record.document_id, ...getAllChildrenKeys(record)];

    if (selected) {
      keys = [...new Set([...keys, ...selfAndChildren])];
    } else {
      keys = keys.filter((k) => !selfAndChildren.includes(k));
      // 取消子项时同步移除祖先文件夹，避免批量操作误删整棵子树
      const ancestorIds = TreeUtils.findAncestorFolderIds(
        tableData,
        record.document_id!,
      );
      keys = keys.filter((k) => !ancestorIds.includes(k));
    }
    setSelectedRowKeys(keys);
  };

  // 处理展开/收起
  const handleExpand = (expanded: boolean, record: TreeNode) => {
    if (!record.document_id) {
      return;
    }

    let newExpandedRowKeys = [...expandedRowKeys];

    if (expanded) {
      // 展开节点
      newExpandedRowKeys.push(record.document_id);
      // 加载子节点数据
      getDocumentData({
        pId: record.document_id,
        level: record.level + 1,
        parentNode: record,
      });
    } else {
      // 收起节点
      newExpandedRowKeys = newExpandedRowKeys.filter(
        (key) => key !== record.document_id,
      );
    }

    setExpandedRowKeys(newExpandedRowKeys);
  };

  // 删除知识
  const handleDelete = (records: TreeNode[]) => {
    if (records.length === 0) {
      message.warning("请选择要删除的知识");
      return;
    }
    Modal.confirm({
      title: "删除知识",
      content: `确定删除${records.length > 1 ? "" : `【${records[0].display_name}】`}知识，删除会同时把子知识同步删除，确定删除吗？`,
      onOk: () => {
        DocumentServiceApi()
          .documentServiceBatchDeleteDocument({
            dataset: detail?.dataset_id || "",
            batchDeleteDocumentRequest: {
              parent: "",
              names: records.map((item) => item.document_id!),
            },
          })
          .then(() => {
            message.success("删除成功");
            setSelectedRowKeys([]);
            setExpandedRowKeys([]);
            getDocumentData({ pId: "", level: 0, page: 1 });
            getDetail();
          })
          .catch(() => {
            message.error("删除失败");
          });
      },
    });
  };

  // 重命名知识和文件夹
  const onRename = (data: RenameFormItem): Promise<void> => {
    if (!currentNode) {
      return Promise.resolve();
    }
    DocumentServiceApi()
      .documentServiceUpdateDocument({
        dataset: detail.dataset_id!,
        document: currentNode.document_id!,
        doc: {
          display_name:
            data.name +
            (currentNode.data_source_type === DocDataSourceTypeEnum.LocalFile
              ? FileUtils.getSuffix(currentNode.display_name || "", true)
              : ""),
          tags: data.tags,
        },
      })
      .then(() => {
        // 刷新后自动同步展开态，避免双击问题。
        if (!currentNode.isLeaf && currentNode.document_id) {
          setExpandedRowKeys((prev) =>
            prev.filter((key) => key !== currentNode.document_id),
          );
        }
        if (currentNode.isLeaf) {
          // 子级文件编辑后刷新根列表，避免继续携带 p_id。
          if (currentNode.p_id) {
            setExpandedRowKeys((prev) =>
              prev.filter((key) => key !== currentNode.p_id),
            );
          }
          getDocumentData({
            pId: "",
            level: 0,
            page: pagination.current,
            pageSize: pagination.pageSize,
          });
          return;
        }
        getDocumentData({
          pId: currentNode.p_id || "",
          level: currentNode.level,
        });
      })
      .finally(() => {
        setCurrentNode(null);
      });
    return Promise.resolve();
  };

  // 打开标签编辑弹窗
  const handleOpenTagEdit = (record: TreeNode) => {
    setTagEditRecord(record);
    setShowTagEditModal(true);
  };

  // 关闭标签编辑弹窗
  const handleCloseTagEdit = () => {
    setShowTagEditModal(false);
    setTagEditRecord(null);
  };

  // 标签编辑成功后的回调
  const handleTagEditSuccess = () => {
    if (tagEditRecord) {
      // 若修改的是文件夹且当前处于展开态：更新成功后收起该文件夹，避免出现“子项已收回但三角仍展开”的不一致
      if (
        tagEditRecord.type === DocTypeEnum.Folder &&
        tagEditRecord.document_id &&
        expandedRowKeys.includes(tagEditRecord.document_id)
      ) {
        setExpandedRowKeys((prev) =>
          prev.filter((k) => k !== tagEditRecord.document_id),
        );
      }

      if (tagEditRecord.p_id) {
        const parentNode = TreeUtils.findNode(
          tableData,
          (node: TreeNode) => node.document_id === tagEditRecord.p_id,
        );
        getDocumentData({
          pId: tagEditRecord.p_id,
          level: tagEditRecord.level,
          parentNode: parentNode || undefined,
        });
        return;
      }
      getDocumentData({
        pId: "",
        level: 0,
        page: pagination.current,
        pageSize: pagination.pageSize,
      });
    }
  };

  const resolveBatchSelectionMeta = async (ids: string[]) => {
    const datasetId = detail.dataset_id || "";
    const folderIds = new Set<string>();
    const directDocumentIds = new Set<string>();
    const leafMap = new Map<string, BatchMoveDocument>();

    const appendLeafDoc = (
      doc: Partial<TreeNode>,
      isDirectSelection = false,
    ) => {
      const documentId = doc.document_id || "";
      if (!documentId) {
        return;
      }
      if (isDirectSelection) {
        directDocumentIds.add(documentId);
      }
      leafMap.set(documentId, {
        documentId,
        parentId: doc.p_id || "",
        dataSourceType: (doc.data_source_type as string) || "",
      });
    };

    const classifySelected = async (id: string) => {
      const node = TreeUtils.findNode(
        tableData,
        (n: TreeNode) => n.document_id === id,
      ) as TreeNode | undefined;
      const type = node?.type;
      if (type) {
        if (type === DocTypeEnum.Folder) {
          folderIds.add(id);
        } else {
          appendLeafDoc(node, true);
        }
        return;
      }
      try {
        const res = await DocumentServiceApi().documentServiceGetDocument({
          dataset: datasetId,
          document: id,
        });
        const doc = res.data as unknown as TreeNode;
        if (doc?.type === DocTypeEnum.Folder) {
          folderIds.add(id);
          return;
        }
        appendLeafDoc(doc, true);
      } catch (e) {
        console.error("Failed to load document:", e);
      }
    };

    await Promise.all(ids.map(classifySelected));

    const visitedFolder = new Set<string>();
    const folderQueue = Array.from(folderIds);
    for (let i = 0; i < folderQueue.length; i += 1) {
      const folderId = folderQueue[i];
      if (visitedFolder.has(folderId)) {
        continue;
      }
      visitedFolder.add(folderId);
      try {
        const res = await DocumentServiceApi().documentServiceSearchDocuments({
          dataset: datasetId,
          searchDocumentsRequest: {
            parent: "",
            p_id: folderId,
            keyword: "",
            page_size: 10000,
          },
        });
        (res.data.documents || []).forEach((doc) => {
          const id = doc.document_id || "";
          if (!id) {
            return;
          }
          if (doc.type === DocTypeEnum.Folder) {
            if (!visitedFolder.has(id)) {
              folderQueue.push(id);
            }
            return;
          }
          appendLeafDoc(doc as unknown as TreeNode);
        });
      } catch (e) {
        console.error("Failed to list folder documents:", e);
      }
    }

    return { folderIds, directDocumentIds, leafMap };
  };

  const resolveBatchEditTagsMeta = async (ids: string[]) => {
    const { folderIds, directDocumentIds, leafMap } =
      await resolveBatchSelectionMeta(ids);

    return {
      selectedFileCount: leafMap.size,
      folderIds: Array.from(folderIds),
      documentIds: Array.from(directDocumentIds),
    };
  };

  const doOpenBatchEditTags = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning("请至少选择一个文件");
      return;
    }
    const key = "batchEditTagsResolving";
    message.open({
      key,
      type: "loading",
      content: "正在统计已选中文档数量...",
      duration: 0,
    });
    try {
      const { selectedFileCount, folderIds, documentIds } =
        await resolveBatchEditTagsMeta(selectedRowKeys);
      if (selectedFileCount === 0) {
        message.warning("所选内容下没有可操作的文件");
        return;
      }
      setBatchTagEditState({
        showModal: true,
        documentIds,
        folderIds,
        selectedFileCount,
      });
    } finally {
      message.destroy(key);
    }
  };

  const resolveBatchMoveMeta = async (ids: string[]) => {
    const { leafMap } = await resolveBatchSelectionMeta(ids);

    return {
      selectedFileCount: leafMap.size,
      documents: Array.from(leafMap.values()),
    };
  };

  const doOpenBatchMove = async () => {
    if (!hasWritePermission) {
      message.warning("当前账号没有写权限");
      return;
    }
    if (selectedRowKeys.length === 0) {
      message.warning("请至少选择一个文件");
      return;
    }
    const key = "batchMoveResolving";
    message.open({
      key,
      type: "loading",
      content: "正在统计已选中文档数量...",
      duration: 0,
    });
    try {
      const { selectedFileCount, documents } =
        await resolveBatchMoveMeta(selectedRowKeys);
      if (selectedFileCount === 0) {
        message.warning("所选内容下没有可移动的文件");
        return;
      }
      setBatchMoveState({
        showModal: true,
        documents,
        selectedFileCount,
      });
    } finally {
      message.destroy(key);
    }
  };

  // 下载知识（提前定义供操作列快捷按钮使用）
  const onDownload = (record: TreeNode) => {
    const link = document.createElement("a");
    link.target = "_blank";
    link.href = record.uri || "";
    link.download = record.display_name || "";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 表格列配置
  const columns = [
    {
      title: (
        <div className="flex items-center">
          <Button type="link" size="small" className="mr-2" icon={<span />} />
          <Checkbox
            checked={
              selectedRowKeys.length > 0 &&
              selectedRowKeys.length === getAllKeys(tableData).length
            }
            indeterminate={
              selectedRowKeys.length > 0 &&
              selectedRowKeys.length < getAllKeys(tableData).length
            }
            onChange={(e) => handleSelectAll(e.target.checked)}
          />
          <span className="ml-3">知识</span>
        </div>
      ),
      dataIndex: "display_name",
      width: 500,
      render: (text: string, record: TreeNode) => {
        const isFolder = record.type === DocTypeEnum.Folder;
        const isExpanded = expandedRowKeys.includes(record.document_id || "");

        return (
          <div
            className="flex w-full items-center gap-2"
            style={{ paddingLeft: record.level * 20 }}
          >
            <Button
              icon={
                isExpanded ? (
                  <CaretDownOutlined />
                ) : isFolder ? (
                  <CaretRightOutlined />
                ) : (
                  <span />
                )
              }
              type="text"
              size="small"
              onClick={() => {
                if (record.type === DocTypeEnum.Folder) {
                  handleExpand(!isExpanded, record);
                  return;
                }
              }}
            />
            <Checkbox
              checked={
                isFolder
                  ? isFolderFullySelected(record)
                  : selectedRowKeys.includes(record.document_id || "")
              }
              onChange={(e) => handleSelect(record, e.target.checked)}
            />
            <Button
              size="small"
              type="link"
              icon={
                isFolder ? (
                  isExpanded ? (
                    <FolderOpenOutlined />
                  ) : (
                    <FolderOutlined />
                  )
                ) : (
                  <BookOutlined />
                )
              }
            />
            <Tooltip title={text} placement="topLeft">
              <a
                className="flex-1"
                onClick={() => {
                  if (record.type === DocTypeEnum.Folder) {
                    handleExpand(!isExpanded, record);
                    return;
                  }
                  navigate({
                    pathname: `/knowledge/${detail.dataset_id}/${record.document_id}`,
                  });
                }}
              >
                <span>{text}</span>
              </a>
            </Tooltip>
          </div>
        );
      },
    },
    {
      title: "标签",
      dataIndex: "tags",
      width: 120,
      render: (tags: string[], record: TreeNode) => {
        if (record.type === DocTypeEnum.Folder) {
          return <span>-</span>;
        }
        if (!tags || tags.length === 0) {
          return (
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span>-</span>
              {hasWritePermission && (
                <Button
                  type="text"
                  size="small"
                  icon={<EditFilled style={{ color: "#1890ff" }} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleOpenTagEdit(record);
                  }}
                  style={{ padding: 0, minWidth: "auto", height: "auto" }}
                />
              )}
            </div>
          );
        }
        return (
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <div
              style={{
                display: "flex",
                gap: "4px",
                overflowX: "auto",
                overflowY: "hidden",
                maxWidth: "100%",
                paddingBottom: "2px",
                WebkitOverflowScrolling: "touch",
                flex: 1,
              }}
              className="tags-scroll-container"
            >
              {tags.map((tag) => (
                <Tag
                  key={tag}
                  style={{ flexShrink: 0, margin: 0, whiteSpace: "nowrap" }}
                >
                  {tag}
                </Tag>
              ))}
            </div>
            {hasWritePermission && (
              <Button
                type="text"
                size="small"
                icon={<EditFilled style={{ color: "#1890ff" }} />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpenTagEdit(record);
                }}
                style={{
                  padding: 0,
                  minWidth: "auto",
                  height: "auto",
                  flexShrink: 0,
                }}
              />
            )}
          </div>
        );
      },
    },
    {
      title: "所在目录",
      dataIndex: "rel_path",
      width: 120,
      render: (rel_path: string) => {
        const kbName = detail.display_name || "-";
        if (!rel_path?.length) {
          return kbName;
        }

        const parts = rel_path.split("/").filter(Boolean);
        if (parts.length >= 2) {
          return `${kbName}/${parts[0]}`;
        }
        return kbName;
      },
    },
    {
      title: "解析状态",
      dataIndex: "document_stage",
      width: 120,
      render: (document_stage: string) => {
        return DocumentStageEnum[
          document_stage as keyof typeof DocumentStageEnum
        ];
      },
    },
    {
      title: "知识类型",
      dataIndex: "type",
      width: 120,
      render: (type: string, record: TreeNode) => {
        if (type === DocTypeEnum.Folder) {
          return "文件夹";
        }
        return FileUtils.getSuffix(record.display_name || "") || "未知";
      },
    },
    {
      title: "大小",
      dataIndex: "document_size",
      width: 120,
      render: (_: number, record: TreeNode) => {
        return FileUtils.formatFileSize(record.document_size);
      },
    },
    {
      title: "更新日期",
      dataIndex: "update_time",
      width: 180,
      render: (text: string) => moment(text).format(TIME_FORMAT),
    },
    {
      title: "更新人",
      dataIndex: "creator",
      width: 120,
    },
    {
      title: "操作",
      key: "action",
      width: 140,
      fixed: "right",
      render: (record: TreeNode) => {
        const canDownload =
          hasWritePermission || hasOnlyReadPermission || hasUploadPermission;
        if (!canDownload) return null;

        const downloadBtn = (
          <Button type="link" size="small" onClick={() => onDownload(record)}>
            下载
          </Button>
        );
        const importBtn = (
          <Button
            type="link"
            size="small"
            onClick={() => {
              const parents = TreeUtils.findParents(
                tableData,
                record.document_id || "",
              );
              onImportKnowledge({
                targetPath: parents.map((item) => item.display_name).join("/"),
                p_id: record.document_id,
              });
            }}
          >
            导入文件
          </Button>
        );

        // 只读者或上传者（无写权限）：文件可下载，上传者还可对文件夹导入，无更多操作
        if (!hasWritePermission) {
          if (record.isLeaf) return downloadBtn;
          return hasUploadPermission ? importBtn : null;
        }

        const isParsePending =
          record.document_stage === DocDocumentStageEnum.DocumentParsing;
        const isUnParse =
          record.document_stage === DocDocumentStageEnum.DocumentUploaded;

        const defaultItems: MenuProps["items"] = [
          {
            key: "rename",
            label: "编辑",
          },
          {
            key: "copy",
            label: "复制",
            disabled: !detail?.acl?.includes("DATASET_READ"),
          },
          {
            key: "move",
            label: "移动",
            disabled: !detail?.acl?.includes("DATASET_WRITE"),
          },
        ];

        const isLeftItems: MenuProps["items"] = [...defaultItems];
        // 非解析中状态，添加解析和重新解析操作
        if (!isParsePending) {
          // 未解析状态，添加解析操作，否则未重新解析
          if (isUnParse) {
            isLeftItems.push({
              key: "parse",
              label: "解析",
            });
          } else {
            isLeftItems.push({
              key: "reparse",
              label: "重新解析",
            });
          }
        }
        isLeftItems.push({ key: "delete", label: "删除", danger: true });
        const notLeafItems: MenuProps["items"] = [
          {
            key: "rename",
            label: "编辑",
          },
          { key: "delete", label: "删除", danger: true },
        ];
        return (
          <div>
            {record.isLeaf ? downloadBtn : importBtn}
            <Dropdown
              menu={{
                items: record.isLeaf ? isLeftItems : notLeafItems,
                onClick: (e) => {
                  e.domEvent.preventDefault();
                  handleMenuClick(e, record);
                },
              }}
            >
              <Button
                type="link"
                size="small"
                icon={<DownOutlined />}
                iconPosition="end"
              >
                更多
              </Button>
            </Dropdown>
          </div>
        );
      },
    },
  ];

  const tableDataRefresh = () => {
    setTimeout(() => {
      getDocumentData({
        pId: "",
        level: 0,
        page: pagination.current,
        pageSize: pagination.pageSize,
      });
    }, 300);
  };

  const resetSelectionState = () => {
    setSelectedRowKeys([]);
  };

  // 更多操作
  const handleMenuClick = (e: { key: string }, record: TreeNode) => {
    if (!e.key) {
      return;
    }
    if (e.key === "delete") {
      handleDelete([record]);
      return;
    }
    setCurrentNode(record);
    switch (e.key) {
      case "rename": {
        const suffix =
          record.data_source_type === DocDataSourceTypeEnum.LocalFile
            ? FileUtils.getSuffix(record.display_name || "", true)
            : "";
        const reg = new RegExp(suffix + "$");
        knowledgeRenameRef.current?.onOpen({
          title: "编辑",
          form: {
            name: !record.isLeaf ? "编辑文件夹名称" : "编辑知识名称",
            namePlaceholder: !record.isLeaf
              ? "仅支持中英文、数字、下划线，长度不超过30个字符"
              : "请输入知识名称",
            nameLen: 30,
            nameRules: [
              {
                required: true,
                validator: (_: unknown, value: string): Promise<void> => {
                  if (!value) {
                    return Promise.reject(
                      !record.isLeaf ? "清输入文件夹名称" : "请输入知识名称",
                    );
                  }
                  if (!record.isLeaf) {
                    if (!FOLDER_NAME_REG.test(value) || value.length > 30) {
                      return Promise.reject(
                        "仅支持中英文、数字、下划线，长度不超过30个字符",
                      );
                    }
                  } else {
                    if (value.length + suffix.length > 300) {
                      return Promise.reject("长度不超过 300 字符");
                    }
                  }
                  return Promise.resolve();
                },
              },
            ],
            nameAdd: suffix || undefined,
          },
          data: {
            name: record.display_name?.replace(reg, "") || "",
            tags: record.tags,
          },
        });
        break;
      }
      case "download": {
        onDownload(record);
        break;
      }
      case "parse":
        JobServiceApi()
          .jobServiceCreateJob({
            dataset: record?.dataset_id || "",
            job: {
              document_ids: [record?.document_id || ""].filter((i) => !!i),
              job_type: JobJobTypeEnum.JobTypeParseUploaded,
            } as unknown as Job,
          })
          .then(() => {
            message.success("创建解析任务成功");
          })
          .catch((error) => {
            console.log(error);
          })
          .finally(() => {
            setCurrentNode(null);
            getImportingTotal();
            tableDataRefresh();
          });
        break;
      case "reparse":
        restartKnowledgeRef.current?.onOpen({
          title: "重新解析",
          dataset: record?.dataset_id || "",
          ids: [record?.document_id || ""],
        });
        break;
      case "import": {
        const parents = TreeUtils.findParents(
          tableData,
          record.document_id || "",
        );
        onImportKnowledge({
          targetPath: parents.map((item) => item.display_name).join("/"),
          p_id: record.document_id,
        });
        break;
      }
      case "copy": {
        setAction("copy");
        setShowCopyModal(true);
        setCurrentDocInfo(record);
        break;
      }
      case "move": {
        setAction("move");
        setShowCopyModal(true);
        setCurrentDocInfo(record);
        break;
      }
      default:
        break;
    }
  };

  // 获取文档数据 - 合并了加载子节点和获取表格数据的功能
  const getDocumentData = async (params: {
    pId: string;
    level: number;
    parentNode?: TreeNode;
    page?: number;
    pageSize?: number;
  }) => {
    const {
      pId,
      level,
      parentNode,
      page = 1,
      pageSize: customPageSize,
    } = params;

    try {
      // 只在根级别（pId 为空）使用分页
      const isRootLevel = !pId && !parentNode;
      const currentPageSize = customPageSize || pagination.pageSize || 10;

      // 构建请求参数
      const searchParams: {
        parent: string;
        p_id: string;
        keyword: string;
        page_size: number;
        page_token?: string;
      } = {
        parent: "",
        p_id: pId,
        keyword,
        page_size: isRootLevel ? currentPageSize : 10000, // 子节点加载所有数据
      };

      // 根级别使用分页 token
      if (isRootLevel && page) {
        const updatedPagination = {
          ...pagination,
          current: page,
          pageSize: currentPageSize,
        };
        setPagination(updatedPagination);

        searchParams.page_token = UIUtils.generatePageToken({
          page: page - 1,
          pageSize: currentPageSize,
          total: pagination.total || 0,
        });
      }

      const res = await DocumentServiceApi().documentServiceSearchDocuments({
        dataset: detail.dataset_id!,
        searchDocumentsRequest: searchParams,
      });

      const documents = res.data.documents.map((doc: Doc) => ({
        ...doc,
        level: level,
        isLeaf: doc.type !== DocTypeEnum.Folder,
        loaded: false,
      }));
      if (parentNode) {
        // 加载子节点数据
        setTableData((prevData) => {
          const newData = cloneDeep(prevData);
          const updateNode = (nodes: TreeNode[]): TreeNode[] => {
            return nodes.map((node) => {
              if (node.document_id === parentNode.document_id) {
                return {
                  ...node,
                  children: documents as TreeNode[],
                  loaded: true,
                };
              }
              if (node.children) {
                return { ...node, children: updateNode(node.children) };
              }
              return node;
            });
          };
          return updateNode(newData);
        });
        // 如果父节点已选中，则把子节点也选中
        if (
          parentNode.document_id &&
          selectedRowKeys.includes(parentNode.document_id)
        ) {
          const childKeys = documents
            .map((doc) => doc.document_id)
            .filter((id): id is string => Boolean(id));
          setSelectedRowKeys((prev) =>
            Array.from(new Set([...prev, ...childKeys])),
          );
        }
      } else {
        // 获取表格数据（根级别）
        if (isRootLevel) {
          // 根级列表刷新后清理展开态，避免出现“子项已收回但图标仍展开”导致需要点击两次的问题。
          setExpandedRowKeys([]);
        }
        setTableData(documents as TreeNode[]);
        setExpandedRowKeys([]);
        // 更新总数
        if (isRootLevel && res.data.total_size !== undefined) {
          setPagination((prev) => ({ ...prev, total: res.data.total_size }));
        }
      }
    } catch (error) {
      console.error("Failed to load documents:", error);
    }
  };

  // 下载选中知识 - 批量下载
  const downloadCheckedKnowledge = () => {
    if (selectedRowKeys.length === 0) {
      return;
    }
    const records = selectedRowKeys.map((key) =>
      TreeUtils.findNode(tableData, (node: TreeNode) => {
        return node.document_id === key;
      }),
    );
    if (records.length === 0) {
      return;
    }
    records.forEach((record) => onDownload(record));
  };

  // 重解析选中知识 - 批量重解析
  const restartCheckedKnowledge = () => {
    if (selectedRowKeys.length === 0) {
      message.warning("请至少选择一个文件");
      return;
    }
    const records = selectedRowKeys.map((key) =>
      TreeUtils.findNode(
        tableData,
        (node: TreeNode) => node.document_id === key,
      ),
    );
    if (records.length === 0) {
      message.warning("请至少选择一个文件");
      return;
    }
    restartKnowledgeRef.current?.onOpen({
      title: "重解析",
      dataset: detail.dataset_id!,
      ids: records.map((record) => record.document_id || ""),
    });
  };

  const updateDocument = (params?: {
    documentId: string;
    level?: number;
    parentNode?: TreeNode;
  }) => {
    if (!params?.documentId) {
      return;
    }
    getDocumentData({
      pId: params.documentId,
      level: params.level || 0,
      parentNode: params.parentNode,
    });
  };

  // 处理分页变化
  const onTableChange = (newPagination: TablePaginationConfig) => {
    setPagination({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
      total: pagination.total,
    });

    getDocumentData({
      pId: "",
      level: 0,
      page: newPagination.current,
      pageSize: newPagination.pageSize,
    });
  };

  // 暴露给父组件的方法
  useImperativeHandle(ref, () => ({
    getTableData: (params) => {
      getDocumentData({
        pId: params?.pId || "",
        level: params?.level || 0,
        parentNode: params?.parentNode,
      });
    },
    treeData: tableData,
    deleteKnowledge: () => {
      if (selectedRowKeys.length === 0) {
        message.warning("请至少选择一个文件");
        return;
      }
      handleDelete(
        selectedRowKeys.map((key) =>
          TreeUtils.findNode(
            tableData,
            (node: TreeNode) => node.document_id === key,
          ),
        ),
      );
    },
    downloadCheckedKnowledge,
    updateDocument,
    restartCheckedKnowledge: restartCheckedKnowledge,
    openBatchEditTags: () => {
      void doOpenBatchEditTags();
    },
    openBatchMove: () => {
      void doOpenBatchMove();
    },
    refresh: (value: string) => {
      setKeyword(value);
    },
  }));

  useEffect(() => {
    if (detail.dataset_id) {
      // 重置分页到第一页
      setPagination({ current: 1, pageSize: 10, total: 0 });
      getDocumentData({ pId: "", level: 0, page: 1 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.dataset_id]);

  useEffect(() => {
    // 搜索时重置分页到第一页
    setPagination((prev) => ({ ...prev, current: 1 }));
    getDocumentData({ pId: "", level: 0, page: 1 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword]);

  return (
    <div className="h-full w-full overflow-hidden">
      <ListPageTable
        columns={columns as unknown as ColumnType<Record<string, unknown>>[]}
        dataSource={tableData}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
        }}
        onChange={onTableChange}
        rowKey="document_id"
        scroll={{ y: "calc(100vh - 380px)" }}
        expandable={{
          expandedRowKeys,
          onExpand: (expanded, record) =>
            handleExpand(expanded, record as TreeNode),
          expandIcon: () => null, // 隐藏默认的展开图标
        }}
      />
      <RenameModel ref={knowledgeRenameRef} onSubmit={onRename} />
      <RestartKnowledgeModal
        ref={restartKnowledgeRef}
        onFinish={() => {
          setCurrentNode(null);
          getImportingTotal();
          tableDataRefresh();
        }}
        parsers={detail.parsers}
      />
      {showCopyModal && (
        <CopyMoveModal
          cancelFn={() => setShowCopyModal(false)}
          currentData={currentDocInfo as TreeNode}
          action={action}
          onSuccess={() => {
            resetSelectionState();
            setTimeout(() => {
              getImportingTotal();
              tableDataRefresh();
            }, 3000);
          }}
        />
      )}
      {/* 标签编辑弹窗 */}
      <EditTags
        open={showTagEditModal}
        record={tagEditRecord}
        datasetId={detail.dataset_id || ""}
        onCancel={handleCloseTagEdit}
        onSuccess={handleTagEditSuccess}
      />
      {/* 批量标签编辑弹窗 */}
      <BatchEditTags
        open={batchTagEditState.showModal}
        selectedFileCount={batchTagEditState.selectedFileCount}
        documentIds={batchTagEditState.documentIds}
        folderIds={batchTagEditState.folderIds}
        datasetId={detail.dataset_id || ""}
        onCancel={() => {
          setBatchTagEditState({
            showModal: false,
            documentIds: [],
            folderIds: [],
            selectedFileCount: 0,
          });
        }}
        onSuccess={() => {
          resetSelectionState();
          tableDataRefresh();
        }}
      />
      <BatchMoveModal
        open={batchMoveState.showModal}
        datasetId={detail.dataset_id || ""}
        selectedFileCount={batchMoveState.selectedFileCount}
        documents={batchMoveState.documents}
        onCancel={() => {
          setBatchMoveState({
            showModal: false,
            documents: [],
            selectedFileCount: 0,
          });
        }}
        onSuccess={() => {
          resetSelectionState();
          getImportingTotal();
          tableDataRefresh();
        }}
      />
    </div>
  );
});

KnowledgeTable.displayName = "KnowledgeTable";

export default KnowledgeTable;
