import { forwardRef, useImperativeHandle, useState } from "react";
import { Modal, Form, Input, Select } from "antd";
import { Dataset, Algo } from "@/api/generated/knowledge-client";

import { KnowledgeBaseServiceApi } from "@/modules/knowledge/utils/request";
import TagSelect from "../TagSelect";

const { TextArea } = Input;
const INDUSTRY_OPTIONS = [
  "无",
  "通用",
  "经调",
  "行车",
  "线路",
  "站场",
  "轨道",
  "地质",
  "路基",
  "桥梁",
  "隧道",
  "工经",
  "供变电",
  "接触网",
  "电力",
  "信息",
  "信号",
  "通信",
  "环保",
  "室外给排水",
  "风景园林",
  "机械",
  "车辆",
  "机务",
  "动车",
  "建筑",
  "结构",
  "暖通",
  "室内给排水",
  "测绘",
].map((label) => ({ label, value: label }));

export interface ForwardProps {
  onUpdate: (dataset: Dataset) => Promise<void>;
}

export interface UpdateImperativeProps {
  onOpen: (data?: Dataset) => void;
}

const UpdateAppModel = forwardRef<UpdateImperativeProps, ForwardProps>(
  ({ onUpdate }, ref) => {
    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<Dataset>();
    const [tags, setTags] = useState<string[]>([]);
    const [algorithm, setAlgorithm] = useState<Algo[]>([]);

    const [form] = Form.useForm();
    useImperativeHandle(ref, () => ({
      onOpen,
    }));

    function getAlgorithm() {
      KnowledgeBaseServiceApi()
        .datasetServiceListAlgos()
        .then((res) => {
          const list = res.data.algos;
          setAlgorithm(list || []);
        });
    }

    function getTags() {
      KnowledgeBaseServiceApi()
        .datasetServiceAllDatasetTags()
        .then((res) => {
          setTags(res.data.tags);
        });
    }

    function onOpen(sourceData: Dataset | undefined) {
      getTags();
      getAlgorithm();
      setData(sourceData);
      if (sourceData) {
        form.setFieldsValue({
          ...sourceData,
          algo_id: sourceData?.algo?.algo_id,
          industry: sourceData?.industry,
        });
      }
      setVisible(true);
    }

    function onCancel() {
      form.resetFields();
      setVisible(false);
    }

    function onOk() {
      form.validateFields().then(async (values) => {
        const params = { ...values };
        params.algo = algorithm.find((item) => item.algo_id === params.algo_id);
        delete params.algo_id;
        if (loading) {
          return;
        }
        setLoading(true);
        try {
          await onUpdate({ ...params, dataset_id: data?.dataset_id });
          setLoading(false);
          onCancel();
        } catch (error) {
          setLoading(false);
          console.error("Update knowledge base error: ", error);
        }
      });
    }

    return (
      <Modal
        open={visible}
        title={`${data ? "编辑" : "创建"}知识库`}
        centered
        onCancel={onCancel}
        onOk={onOk}
        width={576}
        okButtonProps={{ disabled: loading }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="display_name"
            label={"知识库名称"}
            required
            rules={[
              { required: true, message: "请输入知识库名称" },

              {
                pattern: /^[\u4e00-\u9fa5a-zA-Z0-9-_\.]{1,100}$/, // eslint-disable-line
                message: "名称支持中英文、数字、-、_、.，长度不超过 100 个字符",
              },
            ]}
          >
            <Input
              placeholder={
                "名称支持中英文、数字、-、_、.，长度不超过 100 个字符"
              }
              maxLength={100}
            />
          </Form.Item>
          <Form.Item
            name="desc"
            label={"知识库描述"}
            required
            rules={[{ required: true, message: "请输入知识库描述" }]}
          >
            <TextArea
              placeholder={"长度不超过 300 个字符"}
              showCount
              maxLength={300}
              autoSize={{ minRows: 2, maxRows: 6 }}
            />
          </Form.Item>
          <Form.Item
            name="industry"
            label="知识库专业"
            initialValue={undefined}
            rules={[{ required: true, message: "请选择知识库专业" }]}
          >
            <Select options={INDUSTRY_OPTIONS} placeholder="请选择知识库专业" />
          </Form.Item>
          <Form.Item
            name="algo_id"
            label="解析算法"
            initialValue={null}
            rules={[{ required: true, message: "请选择解析算法" }]}
          >
            <Select
              options={algorithm.map((item) => ({
                label: item.display_name,
                value: item.algo_id,
              }))}
              disabled={!!data?.dataset_id}
              placeholder="请选择解析算法"
            />
          </Form.Item>
          <Form.Item
            name="tags"
            label={"知识库标签"}
            rules={[{ required: true, message: "请选择知识库标签" }]}
          >
            <TagSelect tags={tags} />
          </Form.Item>
        </Form>
      </Modal>
    );
  },
);

UpdateAppModel.displayName = "UpdateAppModel";

export default UpdateAppModel;
