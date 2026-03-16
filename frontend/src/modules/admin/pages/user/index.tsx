import { useState, useEffect, useCallback } from "react";
import { Table, Button, Space, Tag, Popconfirm, message, Modal, Form, Input, Tooltip } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined, KeyOutlined } from "@ant-design/icons";
import CreateUserModal from "./components/CreateUserModal";
import { createUserApi } from "@/modules/signin/utils/request";
import { validatePassword } from "@/modules/signin/utils/formRules";
import type { UserItem } from "@/api/generated/auth-client";

const PASSWORD_MAX_LENGTH = 32;
const USERNAME_COLUMN_WIDTH = 220;

const UserManagement = () => {
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
      // 后端返回包装格式为 { code: 200, message: "success", data: UserListResponse }
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
      message.error("获取用户列表失败");
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
      // TODO: OpenAPI 目前缺少删除用户的接口，如果是系统设计如此，请确认
      // 如果后端增加了接口，这里应该调用：
      // const api = createUserApi();
      // await api.deleteUserApiUserUserIdDelete({ user_id: userId });
      message.warning("删除接口尚未在 OpenAPI 中定义");
    } catch (error) {
      message.error("删除失败");
    }
  };

  const handleEditRole = (user: UserItem) => {
    setEditingUser(user);
    setIsModalVisible(true);
  };

  const handleResetPassword = (user: UserItem) => {
    Modal.confirm({
      title: `重置用户 ${user.username} 的密码`,
      content: (
        <Form form={resetPasswordForm} layout="vertical">
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: "请输入新密码" },
              {
                validator: async (_, value) => validatePassword(value),
              },
            ]}
          >
            <Input.Password
              placeholder={`请输入新密码，最多 ${PASSWORD_MAX_LENGTH} 个字符`}
              maxLength={PASSWORD_MAX_LENGTH}
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
          message.success("重置密码成功");
          resetPasswordForm.resetFields();
        } catch (error) {
          console.error("Reset password failed:", error);
          message.error("重置密码失败");
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
      title: "用户名",
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
      title: "邮箱",
      dataIndex: "email",
      key: "email",
      width: 180,
      render: (email: string) => email || "-",
    },
    {
      title: "角色",
      dataIndex: "role_name",
      key: "role_name",
      width: 120,
      render: (roleName: string) => (
        <Tag color={roleName?.toLowerCase().includes("admin") ? "blue" : "green"}>
          {roleName || "普通用户"}
        </Tag>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 80,
      render: (status: string) => (
        <Tag color={status === "active" || status === "enabled" ? "success" : "default"}>
          {status === "active" || status === "enabled" ? "正常" : "禁用"}
        </Tag>
      ),
    },
    {
      title: "操作",
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
            编辑角色
          </Button>
          <Button 
            type="link" 
            size="small"
            icon={<KeyOutlined />} 
            onClick={() => handleResetPassword(record)}
          >
            重置密码
          </Button>
          <Popconfirm
            title="确定删除该用户吗？"
            onConfirm={() => handleDelete(record.user_id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
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
    <div style={{ padding: "24px" }}>
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <h2 style={{ margin: 0 }}>用户管理</h2>
          <Input.Search
            placeholder="搜索用户名称"
            allowClear
            onSearch={handleSearch}
            style={{ width: 250 }}
          />
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditingUser(null);
            setIsModalVisible(true);
          }}
        >
          新建用户
        </Button>
      </div>

      <Table 
        columns={columns} 
        dataSource={users} 
        rowKey="user_id" 
        loading={loading}
        tableLayout="fixed"
        scroll={{ x: 800 }}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
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
