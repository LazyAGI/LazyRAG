import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Space, Popconfirm, message, Input, Tooltip, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  TeamOutlined,
  UsergroupAddOutlined,
} from "@ant-design/icons";
import CreateGroupModal from "./components/CreateGroupModal";
import ManageMembersModal from "./components/ManageMembersModal";
import ManagePermissionsModal from "./components/ManagePermissionsModal";
import { createGroupApi, createUsersServiceApi } from "@/modules/signin/utils/request";
import { AgentAppsAuth } from "@/components/auth";
import type { GroupItem } from "@/api/generated/auth-client";

const { Paragraph } = Typography;
const NAME_COLUMN_WIDTH = 220;

const GroupManagement = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isMemberModalVisible, setIsMemberModalVisible] = useState(false);
  const [isPermissionModalVisible, setIsPermissionModalVisible] =
    useState(false);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [editingGroup, setEditingGroup] = useState<GroupItem | null>(null);
  const [selectedGroupForMembers, setSelectedGroupForMembers] =
    useState<GroupItem | null>(null);
  const [selectedGroupForPermissions, setSelectedGroupForPermissions] =
    useState<GroupItem | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [applyingGroupId, setApplyingGroupId] = useState<string | null>(null);

  const userInfo = AgentAppsAuth.getUserInfo();
  const isAdmin = (role?: string) => {
    const normalizedRole = (role || "").trim().toLowerCase();
    return (
      normalizedRole === "admin" ||
      normalizedRole === "system-admin" ||
      normalizedRole === "system_admin" ||
      normalizedRole.endsWith(".admin")
    );
  };
  const isUserAdmin = isAdmin(userInfo?.role);

  const fetchGroups = useCallback(async (page = 1, pageSize = 20, search = "") => {
    setLoading(true);
    try {
      const api = createGroupApi();
      const res = await api.listGroupsApiAuthserviceGroupGet({
        page,
        pageSize,
        search: search || undefined,
      });
      const resData = res.data as any;
      const data = resData.data || resData;

      setGroups(data.groups || []);
      setPagination({
        current: Number(data.page || page),
        pageSize: Number(data.page_size || pageSize),
        total: Number(data.total || 0),
      });
    } catch (error) {
      console.error("Failed to fetch groups:", error);
      message.error(t("admin.fetchGroupsFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGroups(pagination.current, pagination.pageSize, searchTerm);
  }, [fetchGroups]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    fetchGroups(1, pagination.pageSize, value);
  };

  const handleDelete = async (groupId: string) => {
    try {
      const api = createGroupApi();
      await api.deleteGroupApiAuthserviceGroupGroupIdDelete({ groupId });
      message.success(t("admin.deleteSuccess"));
      fetchGroups(pagination.current, pagination.pageSize, searchTerm);
    } catch (error) {
      message.error(t("admin.deleteFailed"));
    }
  };

  const handleEdit = (group: GroupItem) => {
    setEditingGroup(group);
    setIsModalVisible(true);
  };

  const handleViewGroupDetail = (group: GroupItem) => {
    navigate(`/admin/groups/${group.group_id}`);
  };

  const handleAddMembers = (group: GroupItem) => {
    setSelectedGroupForMembers(group);
    setIsMemberModalVisible(true);
  };

  const handleManagePermissions = (group: GroupItem) => {
    setSelectedGroupForPermissions(group);
    setIsPermissionModalVisible(true);
  };

  const handleApplyJoinGroup = async (group: GroupItem) => {
    setApplyingGroupId(group.group_id);
    try {
      const api = createUsersServiceApi();
      await api.userApplyToJoinGroups({ groupId: group.group_id });
      message.success(t("admin.applyJoinGroupSuccess", { groupName: group.group_name }));
    } catch (error) {
      console.error("Failed to apply join group:", error);
    } finally {
      setApplyingGroupId(null);
    }
  };

  const renderEllipsisText = (text?: string, emptyText = "-") => {
    if (!text) {
      return emptyText;
    }

    return (
      <Paragraph
        style={{ marginBottom: 0, overflowWrap: "anywhere" }}
        ellipsis={{ rows: 2, tooltip: text }}
      >
        {text}
      </Paragraph>
    );
  };

  const columns = [
    {
      title: t("admin.groupName"),
      dataIndex: "group_name",
      key: "group_name",
      width: NAME_COLUMN_WIDTH,
      ellipsis: true,
      render: (text: string, record: GroupItem) => (
        isUserAdmin ? (
          <Tooltip title={text}>
            <Button
              type="link"
              style={{ padding: 0, width: "100%", display: "block", textAlign: "left" }}
              onClick={() => handleViewGroupDetail(record)}
            >
              <span
                style={{
                  display: "block",
                  width: "100%",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {text}
              </span>
            </Button>
          </Tooltip>
        ) : (
          <Tooltip title={text}>
            <span
              style={{
                display: "inline-block",
                width: "100%",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {text}
            </span>
          </Tooltip>
        )
      ),
    },
    {
      title: t("admin.description"),
      dataIndex: "remark",
      key: "remark",
      width: 360,
      render: (remark: string) => renderEllipsisText(remark),
    },
    {
      title: t("admin.actions"),
      key: "action",
      width: isUserAdmin ? 200 : 140,
      render: (_: any, record: GroupItem) => (
        <Space size={4} wrap>
          {isUserAdmin ? (
            <>
              <Button
                type="link"
                size="small"
                icon={<UsergroupAddOutlined />}
                onClick={() => handleAddMembers(record)}
              >
                {t("admin.addMembers")}
              </Button>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEdit(record)}
              >
                {t("common.edit")}
              </Button>
              <Popconfirm
                title={t("admin.deleteGroupConfirm")}
                onConfirm={() => handleDelete(record.group_id)}
                okText={t("common.confirm")}
                cancelText={t("common.cancel")}
              >
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                >
                  {t("common.delete")}
                </Button>
              </Popconfirm>
            </>
          ) : (
            <Button
              type="link"
              size="small"
              icon={<UsergroupAddOutlined />}
              loading={applyingGroupId === record.group_id}
              onClick={() => handleApplyJoinGroup(record)}
            >
              {t("admin.applyJoinGroup")}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const handleCreateSuccess = () => {
    setIsModalVisible(false);
    setEditingGroup(null);
    fetchGroups(pagination.current, pagination.pageSize, searchTerm);
  };

  const handleTableChange = (newPagination: any) => {
    fetchGroups(newPagination.current, newPagination.pageSize, searchTerm);
  };

  return (
    <div style={{ padding: "24px" }}>
      <div
        style={{
          marginBottom: "16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <TeamOutlined style={{ fontSize: "20px" }} />
            <h2 style={{ margin: 0 }}>{t("admin.groupManagement")}</h2>
          </div>
          <Input.Search
            placeholder={t("admin.searchGroupName")}
            allowClear
            onSearch={handleSearch}
            style={{ width: 250 }}
          />
        </div>
        {isUserAdmin && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingGroup(null);
              setIsModalVisible(true);
            }}
          >
            {t("admin.newGroup")}
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={groups}
        rowKey="group_id"
        loading={loading}
        tableLayout="fixed"
        scroll={{ x: 980 }}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total) => t("common.totalItems", { total }),
        }}
        onChange={handleTableChange}
      />

      <CreateGroupModal
        visible={isModalVisible}
        editingGroup={editingGroup}
        onCancel={() => {
          setIsModalVisible(false);
          setEditingGroup(null);
        }}
        onSuccess={handleCreateSuccess}
      />

      <ManageMembersModal
        visible={isMemberModalVisible}
        group={selectedGroupForMembers}
        isAdmin={isUserAdmin}
        defaultViewMode={isUserAdmin ? "add" : "list"}
        onCancel={() => {
          setIsMemberModalVisible(false);
          setSelectedGroupForMembers(null);
        }}
      />

      <ManagePermissionsModal
        visible={isPermissionModalVisible}
        group={selectedGroupForPermissions}
        isAdmin={isUserAdmin}
        onCancel={() => {
          setIsPermissionModalVisible(false);
          setSelectedGroupForPermissions(null);
        }}
      />
    </div>
  );
};

export default GroupManagement;
