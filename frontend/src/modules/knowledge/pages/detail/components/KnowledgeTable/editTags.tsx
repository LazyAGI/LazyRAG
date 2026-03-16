import { useEffect, useState, useMemo } from "react";
import { Modal, Form, Select, message } from "antd";
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
  const [form] = Form.useForm();
  const [tagOptions, setTagOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // 加载所有标签选项
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
    if (open && record) {
      const rawTags = record.tags || [];
      const validTags = rawTags.filter(
        (t: string) => t.length <= MAX_TAG_LENGTH,
      );
      if (validTags.length < rawTags.length) {
        message.warning(`标签长度不能超过${MAX_TAG_LENGTH}个字符`);
      }
      form.setFieldsValue({ tags: validTags });
    } else {
      form.resetFields();
    }
  }, [open, record]);

  // 保存标签
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

      message.success("标签更新成功");
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

  // 处理标签变化：限制数量 10 个、单标签长度 25 字符
  const handleTagsChange = (value: string[]) => {
    const validLengthTags = value.filter((tag) => tag.length <= MAX_TAG_LENGTH);
    const hasOverLength = validLengthTags.length < value.length;
    if (hasOverLength) {
      message.warning(`标签长度不能超过${MAX_TAG_LENGTH}个字符`);
    }
    let limitedValue = validLengthTags;
    if (limitedValue.length > 10) {
      message.warning("最多允许选择10个标签", 3);
      limitedValue = limitedValue.slice(0, 10);
    }
    if (limitedValue.length !== value.length || hasOverLength) {
      setTimeout(() => {
        form.setFieldsValue({ tags: limitedValue });
      }, 0);
    }
  };

  // 优化 options 映射，避免每次渲染都重新计算
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
      title="编辑"
      centered
      onCancel={onCancel}
      onOk={handleOk}
      width={576}
      maskClosable={false}
      okButtonProps={{ loading }}
      cancelButtonProps={{ disabled: loading }}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="tags"
          label="文档标签:"
          rules={[{ required: true, message: "请选择文档标签" }]}
        >
          <Select
            mode="tags"
            tokenSeparators={[","]}
            placeholder="请输入新标签或从已有标签中选择"
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
