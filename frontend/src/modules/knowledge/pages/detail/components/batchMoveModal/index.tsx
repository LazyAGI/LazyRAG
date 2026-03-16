import { useEffect, useMemo, useState } from "react";
import { message, Modal, TreeSelect } from "antd";
import type { DefaultOptionType } from "antd/es/select";
import {
  DocumentServiceApi,
  JobServiceApi,
} from "@/modules/knowledge/utils/request";
import {
  DocTypeEnum,
  JobDataSourceTypeEnum,
  JobJobTypeEnum,
} from "@/api/generated/knowledge-client";
import type { BatchMoveDocument } from "../KnowledgeTable";

type TreeOption = Omit<DefaultOptionType, "label"> & {
  title: string;
  value: string;
  key: string;
  type?: string;
};

interface BatchMoveModalProps {
  open: boolean;
  datasetId: string;
  selectedFileCount: number;
  documents: BatchMoveDocument[];
  onCancel: () => void;
  onSuccess: () => void;
}

const BatchMoveModal = ({
  open,
  datasetId,
  selectedFileCount,
  documents,
  onCancel,
  onSuccess,
}: BatchMoveModalProps) => {
  const [treeData, setTreeData] = useState<TreeOption[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<TreeOption | null>(null);
  const [loading, setLoading] = useState(false);

  const rootNode = useMemo<TreeOption>(
    () => ({
      title: "当前知识库",
      value: datasetId,
      key: datasetId,
      dataset_id: datasetId,
      isLeaf: false,
    }),
    [datasetId],
  );

  useEffect(() => {
    if (!open || !datasetId) {
      return;
    }
    setSelectedTarget(null);
    DocumentServiceApi()
      .documentServiceSearchDocuments({
        dataset: datasetId,
        searchDocumentsRequest: { parent: "", page_size: 10000 },
      })
      .then((res) => {
        const children: TreeOption[] = (res?.data?.documents || [])
          .filter((doc) => doc.type === DocTypeEnum.Folder)
          .map((doc) => ({
            ...doc,
            title: doc.display_name || "",
            value: doc.document_id || "",
            key: doc.document_id || "",
            isLeaf: true,
          }))
          .filter((doc) => !!doc.value);
        setTreeData([{ ...rootNode, children }]);
      })
      .catch((error) => {
        console.error("Failed to load folder tree for batch move:", error);
        setTreeData([{ ...rootNode, children: [] }]);
      });
  }, [open, datasetId, rootNode]);

  const handleOk = async () => {
    if (!selectedFileCount || documents.length === 0) {
      message.warning("请至少选择一个文件");
      return;
    }
    if (!selectedTarget?.value) {
      message.warning("请选择移动目标");
      return;
    }
    const targetPid =
      selectedTarget.value === datasetId ? "" : selectedTarget.value;
    const allAlreadyInTarget = documents.every(
      (doc) => doc.parentId === targetPid,
    );
    if (allAlreadyInTarget) {
      message.warning("所选文件已在当前目标目录，无需移动");
      return;
    }
    const dataSourceTypes = new Set(
      documents.map((doc) => doc.dataSourceType).filter(Boolean),
    );
    const moveDataSourceType =
      dataSourceTypes.size === 1
        ? (Array.from(dataSourceTypes)[0] as JobDataSourceTypeEnum)
        : JobDataSourceTypeEnum.DataSourceTypeUnspecified;
    try {
      setLoading(true);
      await JobServiceApi().jobServiceCreateJob({
        dataset: datasetId,
        job: {
          data_source_type: moveDataSourceType,
          target_dataset_id: datasetId,
          target_pid: targetPid,
          target_path:
            selectedTarget.type === DocTypeEnum.Folder
              ? selectedTarget.title
              : "",
          document_ids: documents.map((doc) => doc.documentId),
          job_type: JobJobTypeEnum.JobTypeMove,
        },
      });
      message.info("移动中，请稍后");
      onSuccess();
      onCancel();
    } catch (error) {
      console.error("Failed to create batch move job:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      title="批量移动"
      centered
      width={720}
      maskClosable={false}
      onCancel={onCancel}
      onOk={handleOk}
      okButtonProps={{ loading }}
      cancelButtonProps={{ disabled: loading }}
    >
      <div style={{ marginBottom: 16, color: "var(--color-text-description)" }}>
        已选择 <span style={{ fontWeight: 600 }}>{selectedFileCount}</span>{" "}
        个文档（不含文件夹）
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ minWidth: 60 }}>移动到：</span>
        <TreeSelect
          style={{ width: "100%" }}
          treeData={treeData}
          value={selectedTarget?.value}
          treeDefaultExpandedKeys={[datasetId]}
          placeholder="输入或选择..."
          onSelect={(_value, option) => setSelectedTarget(option as TreeOption)}
          onChange={(_value, _label, extra) => {
            const node = extra?.triggerNode;
            if (node) {
              setSelectedTarget(node as unknown as TreeOption);
            } else {
              setSelectedTarget(null);
            }
          }}
          allowClear
        />
      </div>
    </Modal>
  );
};

export default BatchMoveModal;
