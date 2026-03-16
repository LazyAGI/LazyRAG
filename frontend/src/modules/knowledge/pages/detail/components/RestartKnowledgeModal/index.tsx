import { Ref, forwardRef, useImperativeHandle, useState } from "react";
import { Modal, Form, message, TreeSelect } from "antd";
import type { Job, ParserConfig } from "@/api/generated/knowledge-client";
import { JobServiceApi } from "@/modules/knowledge/utils/request";

interface IData {
  dataset: string;
  ids: string[];
  title: string;
}

export interface IRestartKnowledgeProps {
  onOpen: (data: IData) => void;
}

interface IProps {
  parsers?: Array<ParserConfig>;
  onFinish: () => void;
}

const allParseList = ["all", "document"];

const RestartKnowledgeModal = (
  props: IProps,
  ref: Ref<unknown> | undefined,
) => {
  const { parsers, onFinish } = props;
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [modalInfo, setModalInfo] = useState<IData>();
  const [form] = Form.useForm();

  useImperativeHandle(ref, () => ({
    onOpen,
  }));

  const onOpen = (data: IData) => {
    setVisible(true);
    setModalInfo(data);
  };

  const onCancel = () => {
    setVisible(false);
    form.resetFields();
  };

  const onOk = async () => {
    if (!modalInfo) {
      return;
    }
    setLoading(true);
    try {
      const { dataset, ids } = modalInfo;
      const { reparse_groups } = (await form.validateFields()) || {};

      await JobServiceApi().jobServiceCreateJob({
        dataset,
        job: {
          document_ids: ids.filter((i) => !!i),
          // reparse: true,
          job_type: "JOB_TYPE_REPARSE",
          reparse_groups: reparse_groups.filter(
            (v: string) => !allParseList.includes(v),
          ),
        } as Job,
      });
      message.success("创建重解析任务成功");
      onFinish?.();
      onCancel();
    } catch (error) {
      console.log(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={visible}
      destroyOnHidden
      title={modalInfo?.title}
      centered
      onCancel={onCancel}
      onOk={onOk}
      width={459}
      height={300}
      okButtonProps={{ disabled: loading }}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="reparse_groups"
          label={"重解析切片"}
          rules={[{ required: true, message: "请选择重解析切片" }]}
          required
        >
          <TreeSelect multiple treeData={formatOptions(parsers || [])} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

const parseTypeMap = {
  // 这版没有预览标签暂时屏蔽.
  // PARSE_TYPE_CONVERT: '预览',
  PARSE_TYPE_SPLIT: "文档切片",
  PARSE_TYPE_QA: "文档问答对",
  PARSE_TYPE_SUMMARY: "文档总结",
  PARSE_TYPE_IMAGE_CAPTION: "图片信息提取",
};

/** 格式化切片筛选 */
function formatOptions(parsers: Array<ParserConfig>) {
  if (!parsers || !parsers.length) {
    return [];
  }
  const documentChild: {
    title: string | undefined;
    value: string | undefined;
  }[] = [];
  const options = [
    { title: "全部切片", value: "all" },
    { title: "文档切片", value: "document" },
  ];

  parsers.forEach((p) => {
    if (p.type === "PARSE_TYPE_SPLIT") {
      documentChild.push({
        title: p.name,
        value: p.name,
      });
    } else if (parseTypeMap[p.type as keyof typeof parseTypeMap]) {
      options.push({
        title: parseTypeMap[p.type as keyof typeof parseTypeMap],
        value: p?.name || "",
      });
    }
  });
  if (documentChild.length) {
    (
      options[1] as {
        title: string;
        value: string;
        children?: typeof documentChild;
      }
    ).children = documentChild;
  }

  return options;
}

export default forwardRef(RestartKnowledgeModal);
