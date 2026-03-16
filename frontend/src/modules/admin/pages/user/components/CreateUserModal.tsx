import { Modal, Form, Input, Select, message } from "antd";
import { useState, useEffect } from "react";
import { createUserApi, createRoleApi } from "@/modules/signin/utils/request";
import {
  passwordRules,
  usernameRules,
} from "@/modules/signin/utils/formRules";
import type { UserItem, RoleItem } from "@/api/generated/auth-client";

const USERNAME_MAX_LENGTH = 100;
const EMAIL_MAX_LENGTH = 100;
const PASSWORD_MAX_LENGTH = 32;

interface CreateUserModalProps {
  visible: boolean;
  editingUser?: UserItem | null;
  onCancel: () => void;
  onSuccess: () => void;
}

const CreateUserModal = ({ visible, editingUser, onCancel, onSuccess }: CreateUserModalProps) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<RoleItem[]>([]);

  const fetchRoles = async () => {
    try {
      const api = createRoleApi();
      const res = await api.listRolesApiAuthserviceRoleGet();
      // 解析后端包装格式 { code: 200, message: "success", data: RoleItem[] }
      const resData = res.data as any;
      const roleList = resData.data || resData || [];
      setRoles(roleList);

      if (!editingUser) {
        const currentRole = form.getFieldValue("role");
        const hasMatchedRole = roleList.some((role: RoleItem) => role.id === currentRole);

        if (!hasMatchedRole) {
          const defaultRole =
            roleList.find((role: RoleItem) => role.name?.toLowerCase() === "user") || roleList[0];

          if (defaultRole?.id) {
            form.setFieldValue("role", defaultRole.id);
          }
        }
      }
    } catch (error) {
      console.error("Failed to fetch roles:", error);
    }
  };

  useEffect(() => {
    if (visible) {
      fetchRoles();
      if (editingUser) {
        form.setFieldsValue({
          username: editingUser.username,
          email: editingUser.email,
          role: editingUser.role_id,
        });
      } else {
        form.resetFields();
      }
    }
  }, [visible, editingUser, form]);

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      const userApi = createUserApi();
      if (editingUser) {
        await userApi.setUserRoleApiAuthserviceUserUserIdPatch({
          userId: editingUser.user_id,
          userRoleBody: { role_id: values.role },
        });
        message.success("修改角色成功");
      } else {
        await userApi.createUserApiAuthserviceUserPost({
          createUserBody: {
            username: values.username,
            password: values.password,
            role_id: values.role,
            ...(values.email ? { email: values.email } : {}),
          },
        });
        message.success("用户创建成功");
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
      title={editingUser ? "编辑角色" : "新建用户"}
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
          name="username"
          label="用户名"
          rules={[
            ...usernameRules,
            { max: USERNAME_MAX_LENGTH, message: `用户名不能超过 ${USERNAME_MAX_LENGTH} 个字符` },
          ]}
        >
          <Input
            placeholder={`请输入用户名，最多 ${USERNAME_MAX_LENGTH} 个字符`}
            disabled={!!editingUser}
            maxLength={USERNAME_MAX_LENGTH}
            showCount
          />
        </Form.Item>

        {!editingUser && (
          <>
            <Form.Item
              name="email"
              label="邮箱"
              rules={[
                { type: "email", message: "请输入有效的邮箱地址" },
                { max: EMAIL_MAX_LENGTH, message: `邮箱不能超过 ${EMAIL_MAX_LENGTH} 个字符` },
              ]}
            >
              <Input
                placeholder={`请输入邮箱，最多 ${EMAIL_MAX_LENGTH} 个字符`}
                maxLength={EMAIL_MAX_LENGTH}
                showCount
              />
            </Form.Item>

            <Form.Item
              name="password"
              label="密码"
              rules={passwordRules}
            >
              <Input.Password
                placeholder={`请输入密码，最多 ${PASSWORD_MAX_LENGTH} 个字符`}
                maxLength={PASSWORD_MAX_LENGTH}
              />
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              label="确认密码"
              dependencies={['password']}
              hasFeedback
              rules={[
                { required: true, message: "请确认密码" },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入的密码不一致!'));
                  },
                }),
              ]}
            >
              <Input.Password
                placeholder={`请再次输入密码，最多 ${PASSWORD_MAX_LENGTH} 个字符`}
                maxLength={PASSWORD_MAX_LENGTH}
              />
            </Form.Item>
          </>
        )}

        <Form.Item
          name="role"
          label="角色"
          rules={[{ required: true, message: "请选择角色" }]}
        >
          <Select placeholder="请选择角色">
            {roles.map((role: any) => (
              <Select.Option key={role.id} value={role.id}>
                {role.name}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CreateUserModal;
