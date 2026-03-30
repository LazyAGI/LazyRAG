import { useState, useEffect, useCallback } from "react";
import { Table, Button, Space, Tag, Popconfirm, message, Modal, Form, Input, Tooltip } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined, KeyOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import CreateUserModal from "./components/CreateUserModal";
import { createUserApi } from "@/modules/signin/utils/request";
import { validatePassword } from "@/modules/signin/utils/formRules";
import type { UserItem } from "@/api/generated/auth-client";

const PASSWORD_MAX_LENGTH = 32;
const USERNAME_COLUMN_WIDTH = 220;

const UserManagement = () => {
  const { t } = useTranslation();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [resetPasswordForm] = Form.useForm();
  const [searchTerm, setSearchTerm] = useState("");

  const fetchUsers = useCallback(async (page = 1, pageSize = 20, search = "") => {
    setLoading(true);
    try {
      const api = createUserApi();
      const res = await api.listUsersApiAuthserviceUserGet({
        page,
        pageSize,
        search: search || undefined,
      });
      const resData = res.data as any;
      const data = resData.data || resData;

      setUsers(data.users || []);
      setPagination({
        current: Number(data.page || page),
        pageSize: Number(data.page_size || pageSize),
        total: Number(data.total || 0),
      });
    } catch (error) {
      console.error("Failed to fetch users:", error);
      message.error(t("admin.fetchUsersFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers(pagination.current, pagination.pageSize, searchTerm);
  }, [fetchUsers]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    fetchUsers(1, pagination.pageSize, value);
  };

  const handleDelete = async (_userId: string) => {
    try {
      // const api = createUserApi();
      // await api.deleteUserApiUserUserIdDelete({ user_id: userId });
      message.warning(t("admin.deleteUserUnavailable"));
    } catch (error) {
      message.error(t("admin.deleteFailed"));
    }
  };

  const handleEditRole = (user: UserItem) => {
    setEditingUser(user);
    setIsModalVisible(true);
  };

  const handleResetPassword = (user: UserItem) => {
    Modal.confirm({
      title: t("admin.resetUserPasswordTitle", { username: user.username }),
      content: (
        <Form form={resetPasswordForm} layout="vertical">
          <Form.Item
            name="new_password"
            label={t("admin.newPassword")}
            rules={[
              { required: true, message: t("admin.enterNewPasswordRequired") },
              {
                validator: async (_, value) => validatePassword(value),
              },
            ]}
          >
            <Input.Password
              placeholder={t("admin.enterNewPassword", { max: PASSWORD_MAX_LENGTH })}
              maxLength={PASSWORD_MAX_LENGTH}
              autoComplete="new-password"
            />
          </Form.Item>
        </Form>
      ),
      onOk: async () => {
        try {
          const values = await resetPasswordForm.validateFields();
          const api = createUserApi();
          await api.resetPasswordApiAuthserviceUserUserIdResetPasswordPatch({
            userId: user.user_id,
            resetPasswordBody: { new_password: values.new_password },
          });
          message.success(t("admin.resetPasswordSuccess"));
          resetPasswordForm.resetFields();
        } catch (error) {
          console.error("Reset password failed:", error);
          message.error(t("admin.resetPasswordFailed"));
          return Promise.reject();
        }
      },
      onCancel: () => {
        resetPasswordForm.resetFields();
      },
    });
  };

  const columns = [
    {
      title: t("admin.username"),
      dataIndex: "username",
      key: "username",
      width: USERNAME_COLUMN_WIDTH,
      ellipsis: true,
      render: (username: string) => (
        <Tooltip title={username}>
          <span
            style={{
              display: "block",
              width: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {username}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t("admin.email"),
      dataIndex: "email",
      key: "email",
      width: 180,
      render: (email: string) => email || "-",
    },
    {
      title: t("admin.role"),
      dataIndex: "role_name",
      key: "role_name",
      width: 120,
      render: (roleName: string) => (
        <Tag color={roleName?.toLowerCase().includes("admin") ? "blue" : "green"}>
          {roleName || t("admin.normalUser")}
        </Tag>
      ),
    },
    {
      title: t("admin.status"),
      dataIndex: "status",
      key: "status",
      width: 80,
      render: (status: string) => (
        <Tag color={status === "active" || status === "enabled" ? "success" : "default"}>
          {status === "active" || status === "enabled" ? t("admin.normal") : t("admin.disabled")}
        </Tag>
      ),
    },
    {
      title: t("admin.actions"),
      key: "action",
      fixed: 'right' as const,
      width: 240,
      render: (_: any, record: UserItem) => (
        <Space size={0}>
          <Button 
            type="link" 
            size="small"
            icon={<EditOutlined />} 
            onClick={() => handleEditRole(record)}
          >
            {t("admin.editUserRole")}
          </Button>
          <Button 
            type="link" 
            size="small"
            icon={<KeyOutlined />} 
            onClick={() => handleResetPassword(record)}
          >
            {t("admin.resetPassword")}
          </Button>
          <Popconfirm
            title={t("admin.deleteUserConfirm")}
            onConfirm={() => handleDelete(record.user_id)}
            okText={t("common.confirm")}
            cancelText={t("common.cancel")}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>{t("common.delete")}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleCreateSuccess = () => {
    setIsModalVisible(false);
    setEditingUser(null);
    fetchUsers(pagination.current, pagination.pageSize, searchTerm);
  };

  const handleTableChange = (newPagination: any) => {
    fetchUsers(newPagination.current, newPagination.pageSize, searchTerm);
  };

  return (
    <div className="admin-page">
      <div className="admin-page-toolbar">
        <div className="admin-page-toolbar-left">
          <h2 className="admin-page-title">{t("admin.userManagement")}</h2>
          <Input.Search
            placeholder={t("admin.searchUsername")}
            allowClear
            onSearch={handleSearch}
            className="admin-page-search"
          />
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          className="admin-page-primary-button"
          onClick={() => {
            setEditingUser(null);
            setIsModalVisible(true);
          }}
        >
          {t("admin.createUser")}
        </Button>
      </div>

      <Table
        className="admin-page-table"
        columns={columns}
        dataSource={users}
        rowKey="user_id"
        loading={loading}
        tableLayout="fixed"
        scroll={{ x: 800 }}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => t("common.totalItems", { total }),
        }}
        onChange={handleTableChange}
      />

      <CreateUserModal
        visible={isModalVisible}
        editingUser={editingUser}
        onCancel={() => {
          setIsModalVisible(false);
          setEditingUser(null);
        }}
        onSuccess={handleCreateSuccess}
      />
    </div>
  );
};

export default UserManagement;
