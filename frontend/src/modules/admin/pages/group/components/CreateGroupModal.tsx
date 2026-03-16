import { Modal, Form, Input, message } from "antd";
import { useState, useEffect } from "react";
import { createGroupApi } from "@/modules/signin/utils/request";
import type { GroupItem } from "@/api/generated/auth-client";

const GROUP_NAME_MAX_LENGTH = 100;
const GROUP_REMARK_MAX_LENGTH = 300;

interface CreateGroupModalProps {
  visible: boolean;
  editingGroup?: GroupItem | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const CreateGroupModal = ({ visible, editingGroup, onCancel, onSuccess }: CreateGroupModalProps) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (visible) {
      if (editingGroup) {
        form.setFieldsValue({
          group_name: editingGroup.group_name,
          remark: editingGroup.remark,
          tenant_id: editingGroup.tenant_id,
        });
      } else {
        form.resetFields();
      }
    }
  }, [visible, editingGroup, form]);

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      const groupApi = createGroupApi();
      if (editingGroup) {
        await groupApi.updateGroupApiAuthserviceGroupGroupIdPatch({
          groupId: editingGroup.group_id,
          groupUpdateBody: {
            group_name: values.group_name,
            remark: values.remark,
            tenant_id: values.tenant_id,
          },
        });
        message.success("修改用户组成功");
      } else {
        await groupApi.createGroupApiAuthserviceGroupPost({
          groupCreateBody: {
            group_name: values.group_name,
            remark: values.remark,
            tenant_id: values.tenant_id,
          },
        });
        message.success("用户组创建成功");
      }
      onSuccess();
    } catch (error: any) {
      console.error("Operation failed:", error);
      const errorMsg = error.response?.data?.message || error.message || "操作失败";
      message.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={editingGroup ? "编辑用户组" : "新建用户组"}
      open={visible}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
      >
        <Form.Item
          name="group_name"
          label="用户组名称"
          rules={[
            { required: true, message: "请输入用户组名称" },
            { max: GROUP_NAME_MAX_LENGTH, message: `用户组名称不能超过 ${GROUP_NAME_MAX_LENGTH} 个字符` },
          ]}
        >
          <Input
            placeholder={`请输入用户组名称，最多 ${GROUP_NAME_MAX_LENGTH} 个字符`}
            maxLength={GROUP_NAME_MAX_LENGTH}
            showCount
          />
        </Form.Item>

        <Form.Item
          name="remark"
          label="描述"
          rules={[
            { max: GROUP_REMARK_MAX_LENGTH, message: `描述不能超过 ${GROUP_REMARK_MAX_LENGTH} 个字符` },
          ]}
        >
          <Input.TextArea
            placeholder={`请输入描述，最多 ${GROUP_REMARK_MAX_LENGTH} 个字符`}
            maxLength={GROUP_REMARK_MAX_LENGTH}
            showCount
            autoSize={{ minRows: 3, maxRows: 6 }}
          />
        </Form.Item>

      </Form>
    </Modal>
  );
};

export default CreateGroupModal;
