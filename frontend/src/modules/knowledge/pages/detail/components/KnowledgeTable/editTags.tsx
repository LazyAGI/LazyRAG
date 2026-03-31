import { useEffect, useState, useMemo } from "react";
import { Modal, Form, Select, message } from "antd";
import { useTranslation } from "react-i18next";
import { DocumentServiceApi } from "@/modules/knowledge/utils/request";
import type { TreeNode } from "./index";

interface EditTagsProps {
  open: boolean;
  record: TreeNode | null;
  datasetId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const MAX_TAG_LENGTH = 25;
const MAX_TAG_COUNT = 10;

function normalizeTags(value: string[]): {
  tags: string[];
  overLength: boolean;
} {
  const valid = (value || []).filter((t) => t.length <= MAX_TAG_LENGTH);
  const overLength = valid.length < (value?.length ?? 0);
  const tags = valid.slice(0, MAX_TAG_COUNT);
  return { tags, overLength };
}

const EditTags = ({
  open,
  record,
  datasetId,
  onCancel,
  onSuccess,
}: EditTagsProps) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      DocumentServiceApi()
        .documentServiceAllDocumentTags()
        .then((res) => {
          setTagOptions(res.data.tags || []);
        })
        .catch((error) => {
          console.error("Failed to load tags:", error);
        });
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (record) {
      const rawTags = record.tags || [];
      const validTags = rawTags.filter(
        (t: string) => t.length <= MAX_TAG_LENGTH,
      );
      if (validTags.length < rawTags.length) {
        message.warning(t("knowledge.singleTagMaxLength", { count: MAX_TAG_LENGTH }));
      }
      form.setFieldsValue({ tags: validTags });
    } else {
      form.resetFields();
    }
  }, [open, record]);

  const handleOk = async () => {
    if (!record) {
      return;
    }

    try {
      const values = await form.validateFields();
      const { tags } = normalizeTags(values.tags || []);
      setLoading(true);
      await DocumentServiceApi().documentServiceUpdateDocument({
        dataset: datasetId,
        document: record.document_id!,
        doc: {
          display_name: record.display_name,
          tags: tags,
        },
      });

      message.success(t("knowledge.tagUpdateSuccess"));
      onSuccess();
      onCancel();
    } catch (error) {
      console.error("Failed to update tags:", error);
      if (error && typeof error === "object" && "errorFields" in error) {
        return;
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTagsChange = (value: string[]) => {
    const validLengthTags = value.filter((tag) => tag.length <= MAX_TAG_LENGTH);
    const hasOverLength = validLengthTags.length < value.length;
    if (hasOverLength) {
      message.warning(t("knowledge.singleTagMaxLength", { count: MAX_TAG_LENGTH }));
    }
    let limitedValue = validLengthTags;
    if (limitedValue.length > 10) {
      message.warning(t("knowledge.maxTenTags"), 3);
      limitedValue = limitedValue.slice(0, 10);
    }
    if (limitedValue.length !== value.length || hasOverLength) {
      setTimeout(() => {
        form.setFieldsValue({ tags: limitedValue });
      }, 0);
    }
  };

  const selectOptions = useMemo(
    () =>
      tagOptions.map((option) => ({
        value: option,
        label: option,
      })),
    [tagOptions],
  );

  return (
    <Modal
      open={open}
      title={t("common.edit")}
      centered
      onCancel={onCancel}
      onOk={handleOk}
      width={576}
      maskClosable={false}
      okButtonProps={{ loading }}
      cancelButtonProps={{ disabled: loading }}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="tags"
          label={`${t("knowledge.tags")}:`}
          rules={[{ required: true, message: t("knowledge.selectDocumentTag") }]}
        >
          <Select
            mode="tags"
            tokenSeparators={[","]}
            placeholder={t("knowledge.inputNewTagOrSelect")}
            options={selectOptions}
            maxCount={MAX_TAG_COUNT}
            onChange={handleTagsChange}
            allowClear
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default EditTags;
