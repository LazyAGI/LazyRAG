import { useState, useEffect, useCallback, useMemo, type CSSProperties } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Table, Button, Space, Input, Tag, Popconfirm, message, Typography, Row, Col } from "antd";
import { 
  PlusOutlined, 
  SearchOutlined, 
  EditOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import { createGroupApi } from "@/modules/signin/utils/request";
import type { GroupDetailResponse, GroupUserItem } from "@/api/generated/auth-client";
import { AgentAppsAuth } from "@/components/auth";
import DetailPageHeader from "@/components/ui/DetailPageHeader";
import ManageMembersModal from "./components/ManageMembersModal";
import CreateGroupModal from "./components/CreateGroupModal";

const { Text } = Typography;

const breakTextStyle: CSSProperties = {
  overflowWrap: "anywhere",
  wordBreak: "break-word",
};

const GroupDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [group, setGroup] = useState<GroupDetailResponse | null>(null);
  const [members, setMembers] = useState<GroupUserItem[]>([]);
  const [memberLoading, setMemberLoading] = useState(false);
  const [memberSearch, setMemberSearch] = useState("");
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [isAddMemberModalVisible, setIsAddMemberModalVisible] = useState(false);

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

  useEffect(() => {
    if (!isUserAdmin) {
      navigate("/admin/groups", { replace: true });
    }
  }, [isUserAdmin, navigate]);

  const fetchGroupDetail = useCallback(async () => {
    if (!id || !isUserAdmin) return;
    setLoading(true);
    try {
      const api = createGroupApi();
      const res = await api.getGroupApiAuthserviceGroupGroupIdGet({ groupId: id });
      const resData = res.data as any;
      const data = resData.data || resData;
      setGroup(data);
    } catch (error) {
      console.error("Failed to fetch group detail:", error);
      message.error("获取用户组详情失败");
    } finally {
      setLoading(false);
    }
  }, [id, isUserAdmin]);

  const fetchMembers = useCallback(async () => {
    if (!id || !isUserAdmin) return;
    setMemberLoading(true);
    try {
      const api = createGroupApi();
      const res = await api.listGroupUsersApiAuthserviceGroupGroupIdUserGet({ groupId: id });
      const resData = res.data as any;
      const memberList = resData.users || resData.data?.users || [];
      setMembers(memberList);
    } catch (error) {
      console.error("Failed to fetch group members:", error);
      message.error("获取成员列表失败");
    } finally {
      setMemberLoading(false);
    }
  }, [id, isUserAdmin]);

  useEffect(() => {
    if (!isUserAdmin) return;
    fetchGroupDetail();
    fetchMembers();
  }, [fetchGroupDetail, fetchMembers, isUserAdmin]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success("已复制到剪贴板");
  };

  const handleRemoveMember = async (userId: string) => {
    if (!id) return;
    try {
      const api = createGroupApi();
      await api.removeGroupUsersApiAuthserviceGroupGroupIdUserRemovePost({
        groupId: id,
        groupRemoveUsersBody: { user_ids: [userId] }
      });
      message.success("移除成员成功");
      fetchMembers();
    } catch (error) {
      console.error("Failed to remove member:", error);
      message.error("移除成员失败");
    }
  };

  const filteredMembers = useMemo(() => {
    return members.filter(m => 
      m.username.toLowerCase().includes(memberSearch.toLowerCase())
    );
  }, [members, memberSearch]);

  const columns = [
    {
      title: "用户名",
      dataIndex: "username",
      key: "username",
    },
    {
      title: "备注",
      dataIndex: "remark",
      key: "remark",
      render: (text: string) => (
        <Text style={breakTextStyle}>
          {text || "-"}
        </Text>
      ),
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      render: (role: string) => (
        <Tag color={role === "admin" ? "orange" : "blue"}>
          {role === "admin" ? "组管理员" : "成员"}
        </Tag>
      ),
    },
    {
      title: "加入时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (text: string) => text || "-",
    },
    {
      title: "操作",
      key: "action",
      width: 200,
      render: (_: any, record: GroupUserItem) => (
        <Space size="middle">
          {/* 这里可以添加 "设为组管理员" 的逻辑，如果 API 支持 */}
          <Popconfirm
            title="确定要将该用户从组中移除吗？"
            onConfirm={() => handleRemoveMember(record.user_id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger size="small">移除成员</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!isUserAdmin) {
    return null;
  }

  return (
    <div style={{ padding: "24px" }}>
      <DetailPageHeader
        breadcrumbs={[
          { 
            title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/admin/groups")}>用户组</span> 
          },
          { title: "用户组详情" }
        ]}
        title={group?.group_name || "用户组详情"}
        onBack={() => navigate("/admin/groups")}
      />

      <Card 
        loading={loading}
        title="基本信息" 
        extra={isUserAdmin && <Button icon={<EditOutlined />} onClick={() => setIsEditModalVisible(true)}>编辑</Button>}
        style={{ marginTop: "24px" }}
      >
        <Row gutter={[24, 16]}>
          <Col span={12}>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Text type="secondary">用户组名</Text>
              <Space>
                <Text strong style={breakTextStyle}>{group?.group_name}</Text>
                <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(group?.group_name || "")} />
              </Space>
            </Space>
          </Col>
          <Col span={12}>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Text type="secondary">用户组ID</Text>
              <Space>
                <Text style={breakTextStyle}>{group?.group_id}</Text>
                <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(group?.group_id || "")} />
              </Space>
            </Space>
          </Col>
          <Col span={12}>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Text type="secondary">备注</Text>
              <Text style={breakTextStyle}>{group?.remark || "-"}</Text>
            </Space>
          </Col>
          <Col span={12}>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Text type="secondary">成员数量</Text>
              <Text>{members.length}</Text>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card title="用户组管理" style={{ marginTop: "24px" }}>
        <div style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Input
            placeholder="请输入用户名"
            prefix={<SearchOutlined />}
            style={{ width: 250 }}
            value={memberSearch}
            onChange={e => setMemberSearch(e.target.value)}
            allowClear
          />
          {isUserAdmin && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsAddMemberModalVisible(true)}>
              添加成员
            </Button>
          )}
        </div>
        <Table
          columns={columns}
          dataSource={filteredMembers}
          rowKey="user_id"
          loading={memberLoading}
          pagination={{ showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
        />
      </Card>

      <CreateGroupModal
        visible={isEditModalVisible}
        editingGroup={group as any}
        onCancel={() => setIsEditModalVisible(false)}
        onSuccess={() => {
          setIsEditModalVisible(false);
          fetchGroupDetail();
        }}
      />

      <ManageMembersModal
        visible={isAddMemberModalVisible}
        group={group as any}
        isAdmin={isUserAdmin}
        defaultViewMode="add"
        onCancel={() => setIsAddMemberModalVisible(false)}
        onSuccess={() => {
          setIsAddMemberModalVisible(false);
          fetchMembers();
        }}
      />
    </div>
  );
};

export default GroupDetail;
