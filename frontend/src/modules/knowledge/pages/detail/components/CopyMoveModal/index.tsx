import {
  DocumentServiceApi,
  JobServiceApi,
} from "@/modules/knowledge/utils/request";
import { CommonModal } from "@/components/ui";
import { message, TreeSelect, TreeSelectProps } from "antd";
import { DefaultOptionType } from "antd/es/select";
import { useEffect, useState } from "react";
import { TreeNode } from "../KnowledgeTable";
import { JobJobTypeEnum } from "@/api/generated/knowledge-client";

type ITreeData = Omit<DefaultOptionType, "label">;
interface CopyMoveModalProps {
  cancelFn: () => void;
  currentData: TreeNode;
  action: "copy" | "move";
  onSuccess?: () => void;
}

function CopyMoveModal(props: CopyMoveModalProps) {
  const { cancelFn, currentData, action, onSuccess } = props;
  const {
    dataset_id = "",
    data_source_type = "DATA_SOURCE_TYPE_UNSPECIFIED",
    document_id = "",
    p_id,
  } = currentData ?? {};
  const [treeData, setTreeData] = useState<ITreeData[]>([]);
  const [selectTreeData, setSelectTreeData] = useState<ITreeData>({});

  console.log(selectTreeData, currentData, "当前选择的参数");

  function updateTreeData(
    list: ITreeData[],
    key: React.Key,
    children: ITreeData[],
  ): ITreeData[] {
    return list.map((node) => {
      if (node.value === key) {
        return { ...node, children };
      }
      if (node.children) {
        return {
          ...node,
          children: updateTreeData(node.children, key, children),
        };
      }
      return node;
    });
  }

  function getKnowledgeDetailFn(params: ITreeData) {
    const isRoot = params.value === dataset_id;
    return DocumentServiceApi()
      .documentServiceSearchDocuments({
        dataset: dataset_id,
        searchDocumentsRequest: {
          parent: isRoot ? "" : (params.value as string),
          page_size: 10000,
        },
      })
      .then((res) => {
        const folderArr = res?.data?.documents
          ?.filter((it) => it.type === "FOLDER")
          ?.map((k) => ({
            ...k,
            title: k.display_name,
            value: k?.document_id,
            isLeaf: true,
            dataset_id,
          }));

        setTreeData((origin) =>
          updateTreeData(origin, params.value as React.Key, folderArr),
        );
      });
  }

  useEffect(() => {
    if (!dataset_id) return;
    const rootNode: ITreeData = {
      title: "当前知识库",
      value: dataset_id,
      key: dataset_id,
      dataset_id: dataset_id,
      isLeaf: false, // Ensure root is expandable
      children: [],
    };
    // Fetch root docs
    DocumentServiceApi()
      .documentServiceSearchDocuments({
        dataset: dataset_id,
        searchDocumentsRequest: { parent: "", page_size: 10000 },
      })
      .then((docRes) => {
        const folderArr = docRes?.data?.documents
          ?.filter((it) => it.type === "FOLDER")
          ?.map((k) => ({
            ...k,
            title: k.display_name,
            value: k?.document_id,
            isLeaf: true,
            dataset_id,
          }));
        rootNode.children = folderArr;
        setTreeData([rootNode]);
      });
  }, [dataset_id]);

  const onLoadData: TreeSelectProps["loadData"] = async (params) => {
    return await getKnowledgeDetailFn(params);
  };

  function successFn() {
    JobServiceApi()
      .jobServiceCreateJob({
        dataset: dataset_id,
        job: {
          data_source_type,
          target_dataset_id: selectTreeData?.dataset_id,
          target_path:
            selectTreeData?.type === "FOLDER"
              ? selectTreeData?.display_name
              : "",
          target_pid:
            selectTreeData?.value === dataset_id
              ? ""
              : (selectTreeData?.value as string),
          document_ids: [document_id],
          document_pid: p_id,
          job_type:
            action === "move"
              ? JobJobTypeEnum.JobTypeMove
              : JobJobTypeEnum.JobTypeCopy,
        },
      })
      .then((res) => {
        console.log(res);
        message.info(action === "move" ? "移动中，请稍后" : "复制中,请稍后");
        onSuccess?.();
        cancelFn();
      });
  }

  function renderContentFn() {
    return (
      <TreeSelect
        style={{ width: "100%" }}
        value={selectTreeData?.value}
        treeDefaultExpandedKeys={[dataset_id]}
        styles={{
          popup: { root: { maxHeight: 400, overflow: "auto" } },
        }}
        placeholder="请选择"
        onSelect={(_id, opt) => setSelectTreeData(opt)}
        loadData={onLoadData}
        treeData={treeData}
      />
    );
  }

  return (
    <CommonModal
      title={action === "move" ? "移动到" : "复制"}
      contentText={renderContentFn()}
      successFn={successFn}
      cancelFn={cancelFn}
    />
  );
}

export default CopyMoveModal;
