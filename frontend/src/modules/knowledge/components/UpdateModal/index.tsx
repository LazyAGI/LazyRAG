import { forwardRef, useImperativeHandle, useState } from "react";
import { Modal, Form, Input, Select } from "antd";
import { useTranslation } from "react-i18next";
import { Dataset, Algo } from "@/api/generated/knowledge-client";

import { KnowledgeBaseServiceApi } from "@/modules/knowledge/utils/request";
import TagSelect from "../TagSelect";

const { TextArea } = Input;

export interface ForwardProps {
  onUpdate: (dataset: Dataset) => Promise<void>;
}

export interface UpdateImperativeProps {
  onOpen: (data?: Dataset) => void;
}

const UpdateAppModel = forwardRef<UpdateImperativeProps, ForwardProps>(
  ({ onUpdate }, ref) => {
    const { t } = useTranslation();
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
        title={data ? t("knowledge.edit") + t("layout.knowledgeBase") : t("knowledge.createKnowledgeBase")}
        centered
        onCancel={onCancel}
        onOk={onOk}
        width={576}
        okButtonProps={{ disabled: loading }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="display_name"
            label={t("knowledge.nameId")}
            required
            rules={[
              { required: true, message: t("common.pleaseInput") + t("layout.knowledgeBase") + t("knowledge.nameId") },

              {
                pattern: /^[\u4e00-\u9fa5a-zA-Z0-9-_\.]{1,100}$/, // eslint-disable-line
                message: t("knowledge.knowledgeNameRule"),
              },
            ]}
          >
            <Input
              placeholder={
                t("knowledge.knowledgeNameRule")
              }
              maxLength={100}
            />
          </Form.Item>
          <Form.Item
            name="desc"
            label={t("knowledge.knowledgeDesc")}
            required
            rules={[{ required: true, message: t("knowledge.inputKnowledgeDesc") }]}
          >
            <TextArea
              placeholder={t("knowledge.maxLength300Chars")}
              showCount
              maxLength={300}
              autoSize={{ minRows: 2, maxRows: 6 }}
            />
          </Form.Item>
          <Form.Item
            name="algo_id"
            label={t("knowledge.parseAlgorithm")}
            initialValue={null}
            rules={[{ required: true, message: t("knowledge.selectParseAlgorithm") }]}
          >
            <Select
              options={algorithm.map((item) => ({
                label: item.display_name,
                value: item.algo_id,
              }))}
              disabled={!!data?.dataset_id}
              placeholder={t("knowledge.selectParseAlgorithm")}
            />
          </Form.Item>
          <Form.Item
            name="tags"
            label={t("knowledge.knowledgeTags")}
            rules={[{ required: true, message: t("knowledge.selectKnowledgeTags") }]}
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
