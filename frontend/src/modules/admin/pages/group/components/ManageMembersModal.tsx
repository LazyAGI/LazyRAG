import {
  Modal as AntdModal,
  Table as AntdTable,
  Button as AntdButton,
  Space as AntdSpace,
  message as AntdMessage,
  Input as AntdInput,
  Tag as AntdTag,
  Popconfirm as AntdPopconfirm,
  Tooltip as AntdTooltip,
} from "antd";
import type { TableColumnsType } from "antd";
import { useState, useEffect, useCallback, useMemo } from "react";
import { createGroupApi, createUserApi } from "@/modules/signin/utils/request";
import type {
  GroupItem,
  GroupUserItem,
  UserItem,
} from "@/api/generated/auth-client";
import {
  SearchOutlined,
  RightOutlined,
  LeftOutlined,
  UsergroupAddOutlined,
  DeleteOutlined,
  PlusOutlined,
  ArrowLeftOutlined,
} from "@ant-design/icons";
import { useStyles } from "@/components/ui/useStyles";

const manageMembersModalCss = `
.manage-members-modal .ant-modal {
  max-width: calc(100vw - 32px);
}

.manage-members-modal__toolbar {
  margin-bottom: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.manage-members-modal__transfer {
  display: flex;
  align-items: stretch;
  gap: 12px;
  min-height: 450px;
}

.manage-members-modal__panel {
  flex: 1 1 0;
  min-width: 0;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.manage-members-modal__panel-header {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.manage-members-modal__search {
  padding: 8px;
}

.manage-members-modal__table {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.manage-members-modal__actions {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  flex: 0 0 auto;
}

.manage-members-modal__break-text {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.manage-members-modal__ellipsis-text {
  display: block;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage-members-modal__empty {
  padding: 40px 0;
  color: #bfbfbf;
}

.manage-members-modal .ant-table-wrapper {
  height: 100%;
}

.manage-members-modal .ant-table-container table {
  table-layout: fixed;
}

.manage-members-modal .ant-pagination {
  margin-inline: 8px;
}

@media (max-width: 960px) {
  .manage-members-modal__transfer {
    flex-direction: column;
    min-height: auto;
  }

  .manage-members-modal__actions {
    flex-direction: row;
    justify-content: center;
  }
}
`;

interface ManageMembersModalProps {
  visible: boolean;
  group: GroupItem | null;
  isAdmin: boolean;
  defaultViewMode?: "list" | "add";
  onCancel: () => void;
  onSuccess?: () => void;
}

enum GroupMemberRole {
  Admin = "admin",
  Member = "member",
}

interface GroupMemberListItem extends GroupUserItem {
  email?: string;
  role: GroupMemberRole | string;
  tenant_ids?: string | string[];
}

const getMemberRoleMeta = (role?: GroupMemberRole | string) => {
  switch ((role || "").trim().toLowerCase()) {
    case GroupMemberRole.Admin:
      return {
        color: "orange",
        label: "组管理员",
      };
    case GroupMemberRole.Member:
      return {
        color: "blue",
        label: "成员",
      };
    default:
      return {
        color: "default",
        label: role || "-",
      };
  }
};

const ManageMembersModal = ({
  visible,
  group,
  isAdmin,
  defaultViewMode = "list",
  onCancel,
  onSuccess,
}: ManageMembersModalProps) => {
  useStyles("manage-members-modal-styles", manageMembersModalCss);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "add">(defaultViewMode);

  // 数据状态
  const [allUsers, setAllUsers] = useState<UserItem[]>([]);
  const [currentMembers, setCurrentMembers] = useState<GroupMemberListItem[]>([]);

  // 穿梭框左右侧选中的 key (user_id)
  const [leftSelectedKeys, setLeftSelectedKeys] = useState<string[]>([]);
  const [rightSelectedKeys, setRightSelectedKeys] = useState<string[]>([]);

  // 右侧（待提交添加的）用户列表
  const [pendingAddUsers, setPendingAddUsers] = useState<UserItem[]>([]);

  // 搜索关键字
  const [leftSearch, setLeftSearch] = useState("");
  const [rightSearch, setRightSearch] = useState("");
  const [memberSearch, setMemberSearch] = useState("");

  // 获取所有用户 (带 200 限制规避)
  const fetchAllUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const userApi = createUserApi();
      const pageSize = 200;
      let page = 1;
      let total = 0;
      const users: UserItem[] = [];
      do {
        const res = await userApi.listUsersApiAuthserviceUserGet({
          page,
          pageSize,
        });
        const resData = res.data as any;
        const data = resData.data || resData || {};
        const currentUsers = data.users || [];
        users.push(...currentUsers);
        total = Number(data.total || users.length);
        page += 1;
      } while (users.length < total);
      setAllUsers(users);
    } catch (error) {
      console.error("Failed to fetch users:", error);
    }
  }, [isAdmin]);

  // 获取当前组成员
  const fetchMembers = useCallback(async () => {
    if (!group) return;
    setLoading(true);
    try {
      const groupApi = createGroupApi();
      const res =
        await groupApi.listGroupUsersApiAuthserviceGroupGroupIdUserGet({
          groupId: group.group_id,
        });
      console.log(res)
      const resData = res.data as any;
      const members = (resData.users || resData.data?.users || []) as GroupMemberListItem[];
      setCurrentMembers(members);
    } catch (error) {
      console.error("Failed to fetch members:", error);
      AntdMessage.error("获取成员列表失败");
    } finally {
      setLoading(false);
    }
  }, [group]);

  useEffect(() => {
    if (visible && group) {
      setViewMode(defaultViewMode);
      fetchMembers();
      if (isAdmin) {
        fetchAllUsers();
      }
      // 重置状态
      setPendingAddUsers([]);
      setLeftSelectedKeys([]);
      setRightSelectedKeys([]);
      setLeftSearch("");
      setRightSearch("");
      setMemberSearch("");
    }
  }, [visible, group, isAdmin, defaultViewMode, fetchAllUsers, fetchMembers]);

  // 左侧待选列表：(全量用户 - 当前成员 - 已移到右侧的用户) 过滤搜索词
  const leftDataSource = useMemo(() => {
    return allUsers.filter((user) => {
      const isMember = currentMembers.some((m) => m.user_id === user.user_id);
      const isPending = pendingAddUsers.some((p) => p.user_id === user.user_id);
      const matchesSearch = user.username
        .toLowerCase()
        .includes(leftSearch.toLowerCase());
      return !isMember && !isPending && matchesSearch;
    });
  }, [allUsers, currentMembers, pendingAddUsers, leftSearch]);

  // 右侧已选列表：(已移到右侧的用户) 过滤搜索词
  const rightDataSource = useMemo(() => {
    return pendingAddUsers.filter((user) =>
      user.username.toLowerCase().includes(rightSearch.toLowerCase()),
    );
  }, [pendingAddUsers, rightSearch]);

  // 移向右侧
  const moveToRight = () => {
    const usersToMove = leftDataSource.filter((u) =>
      leftSelectedKeys.includes(u.user_id),
    );
    setPendingAddUsers((prev) => [...prev, ...usersToMove]);
    setLeftSelectedKeys([]);
  };

  // 移向左侧
  const moveToLeft = () => {
    setPendingAddUsers((prev) =>
      prev.filter((u) => !rightSelectedKeys.includes(u.user_id)),
    );
    setRightSelectedKeys([]);
  };

  // 提交保存添加
  const handleConfirmAdd = async () => {
    if (!group) return;
    if (pendingAddUsers.length === 0) {
      AntdMessage.warning("请选择要添加的用户");
      return;
    }
    setSaving(true);
    try {
      const groupApi = createGroupApi();
      await groupApi.addGroupUsersApiAuthserviceGroupGroupIdUserPost({
        groupId: group.group_id,
        groupAddUsersBody: { user_ids: pendingAddUsers.map((u) => u.user_id) },
      });
      AntdMessage.success("添加成员成功");
      setPendingAddUsers([]);
      fetchMembers();
      setViewMode("list");
      onSuccess?.();
    } catch (error: any) {
      console.error("Add members failed:", error);
      AntdMessage.error(error.response?.data?.message || "添加成员失败");
    } finally {
      setSaving(false);
    }
  };

  // 移除成员
  const handleRemoveMember = async (userId: string) => {
    if (!group) return;
    try {
      const groupApi = createGroupApi();
      await groupApi.removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost({
        groupId: group.group_id,
        groupRemoveUsersBody: { user_ids: [userId] },
      });
      AntdMessage.success("移除成员成功");
      fetchMembers();
      onSuccess?.();
    } catch (error: any) {
      console.error("Remove member failed:", error);
      AntdMessage.error(error.response?.data?.message || "移除成员失败");
    }
  };

  const userColumns: TableColumnsType<UserItem> = [
    {
      title: "用户名",
      dataIndex: "username",
      key: "username",
      width: 220,
      render: (value: string) => (
        <AntdTooltip title={value || "-"}>
          <span className="manage-members-modal__ellipsis-text">
            {value || "-"}
          </span>
        </AntdTooltip>
      ),
    },
    {
      title: "邮箱",
      dataIndex: "email",
      key: "email",
      width: 240,
      render: (value?: string) => (
        <div className="manage-members-modal__break-text">{value || "-"}</div>
      ),
    },
    {
      title: "角色",
      dataIndex: "role_name",
      key: "role_name",
      width: 120,
      render: (roleName?: string) => (
        <AntdTag color={roleName?.toLowerCase().includes("admin") ? "orange" : "blue"}>
          {roleName || "-"}
        </AntdTag>
      ),
    },
  ];

  const memberBaseColumns: TableColumnsType<GroupMemberListItem> = [
    {
      title: "用户名",
      dataIndex: "username",
      key: "username",
      width: 220,
      render: (value: string) => (
        <AntdTooltip title={value || "-"}>
          <span className="manage-members-modal__ellipsis-text">
            {value || "-"}
          </span>
        </AntdTooltip>
      ),
    },
    {
      title: "邮箱",
      dataIndex: "email",
      key: "email",
      width: 240,
      render: (value?: string) => (
        <div className="manage-members-modal__break-text">{value || "-"}</div>
      ),
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      width: 120,
      render: (role?: GroupMemberRole | string) => {
        const { color, label } = getMemberRoleMeta(role);
        return <AntdTag color={color}>{label}</AntdTag>;
      },
    },
  ];

  const memberColumns: TableColumnsType<GroupMemberListItem> = [
    ...memberBaseColumns,
    ...(isAdmin
      ? [
          {
            title: "操作",
            key: "action",
            width: 80,
            render: (_: unknown, record: GroupMemberListItem) => (
              <AntdPopconfirm
                title="确定移除该成员吗？"
                onConfirm={() => handleRemoveMember(record.user_id)}
                okText="确定"
                cancelText="取消"
              >
                <AntdButton
                  type="link"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                >
                  移除
                </AntdButton>
              </AntdPopconfirm>
            ),
          },
        ]
      : []),
  ];

  const filteredMembers = currentMembers.filter((m) => {
    return (
      m.username.toLowerCase().includes(memberSearch.toLowerCase()) ||
      (m.email && m.email.toLowerCase().includes(memberSearch.toLowerCase()))
    );
  });

  return (
    <AntdModal
      title={
        <AntdSpace>
          <UsergroupAddOutlined />
          <span>{group?.group_name} - 成员管理</span>
        </AntdSpace>
      }
      open={visible}
      onCancel={onCancel}
      footer={
        viewMode === "list"
          ? [
              <AntdButton key="close" onClick={onCancel}>
                关闭
              </AntdButton>,
            ]
          : [
              <AntdButton key="cancel" onClick={() => setViewMode("list")}>
                取消
              </AntdButton>,
              <AntdButton
                key="submit"
                type="primary"
                loading={saving}
                onClick={handleConfirmAdd}
              >
                确定添加
              </AntdButton>,
            ]
      }
      width={viewMode === "list" ? 800 : 1080}
      destroyOnHidden
      className="manage-members-modal"
      styles={{
        body: {
          padding: "12px 24px",
          maxHeight: "calc(100vh - 180px)",
          overflowY: "auto",
        },
      }}
    >
      {viewMode === "list" ? (
        <>
          <div className="manage-members-modal__toolbar">
            <AntdInput
              placeholder="搜索成员姓名或邮箱"
              prefix={<SearchOutlined style={{ color: "#bfbfbf" }} />}
              value={memberSearch}
              onChange={(e) => setMemberSearch(e.target.value)}
              style={{ width: 250, maxWidth: "100%" }}
              allowClear
            />
            {isAdmin && (
              <AntdButton
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setViewMode("add")}
              >
                添加成员
              </AntdButton>
            )}
          </div>
          <AntdTable
            dataSource={filteredMembers}
            columns={memberColumns}
            rowKey="user_id"
            loading={loading}
            pagination={{ pageSize: 10, showSizeChanger: true }}
            size="small"
            tableLayout="fixed"
            scroll={{ x: 760 }}
          />
        </>
      ) : (
        <>
          <div style={{ marginBottom: "16px" }}>
            <AntdButton
              icon={<ArrowLeftOutlined />}
              onClick={() => setViewMode("list")}
              style={{ marginBottom: "12px" }}
            >
              返回成员列表
            </AntdButton>
            <div style={{ color: "#666" }}>
              请选择待选用户，并添加至{" "}
              <span style={{ color: "#1890ff", fontWeight: "bold" }}>
                {group?.group_name}
              </span>
            </div>
          </div>

          <div className="manage-members-modal__transfer">
            {/* 左侧：待选择 */}
            <div className="manage-members-modal__panel">
              <div className="manage-members-modal__panel-header">
                <span style={{ fontWeight: "bold" }}>
                  {leftDataSource.length} 项
                </span>
                <span style={{ color: "#999" }}>待选择</span>
              </div>
              <div className="manage-members-modal__search">
                <AntdInput
                  placeholder="搜索待选用户"
                  prefix={<SearchOutlined style={{ color: "#bfbfbf" }} />}
                  value={leftSearch}
                  onChange={(e) => setLeftSearch(e.target.value)}
                  allowClear
                />
              </div>
              <div className="manage-members-modal__table">
                <AntdTable
                  size="small"
                  rowSelection={{
                    selectedRowKeys: leftSelectedKeys,
                    onChange: (keys) => setLeftSelectedKeys(keys as string[]),
                  }}
                  dataSource={leftDataSource}
                  columns={userColumns}
                  rowKey="user_id"
                  tableLayout="fixed"
                  scroll={{ x: 620 }}
                  pagination={{
                    size: "small",
                    pageSize: 10,
                    showSizeChanger: false,
                  }}
                />
              </div>
            </div>

            {/* 中间：操作按钮 */}
            <div className="manage-members-modal__actions">
              <AntdButton
                icon={<RightOutlined />}
                onClick={moveToRight}
                disabled={leftSelectedKeys.length === 0}
                type={leftSelectedKeys.length > 0 ? "primary" : "default"}
              />
              <AntdButton
                icon={<LeftOutlined />}
                onClick={moveToLeft}
                disabled={rightSelectedKeys.length === 0}
                type={rightSelectedKeys.length > 0 ? "primary" : "default"}
              />
            </div>

            {/* 右侧：已选择 */}
            <div className="manage-members-modal__panel">
              <div className="manage-members-modal__panel-header">
                <span style={{ fontWeight: "bold" }}>
                  {rightDataSource.length} 项
                </span>
                <span style={{ color: "#999" }}>已选择</span>
              </div>
              <div className="manage-members-modal__search">
                <AntdInput
                  placeholder="搜索已选用户"
                  prefix={<SearchOutlined style={{ color: "#bfbfbf" }} />}
                  value={rightSearch}
                  onChange={(e) => setRightSearch(e.target.value)}
                  allowClear
                />
              </div>
              <div className="manage-members-modal__table">
                <AntdTable
                  size="small"
                  rowSelection={{
                    selectedRowKeys: rightSelectedKeys,
                    onChange: (keys) => setRightSelectedKeys(keys as string[]),
                  }}
                  dataSource={rightDataSource}
                  columns={userColumns.slice(0, 1)}
                  rowKey="user_id"
                  pagination={false}
                  tableLayout="fixed"
                  scroll={{ x: 320 }}
                  locale={{
                    emptyText: (
                      <div className="manage-members-modal__empty">
                        暂无已选用用户
                      </div>
                    ),
                  }}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </AntdModal>
  );
};

export default ManageMembersModal;
