import { Modal, Table, Button, Checkbox, message, Space } from "antd";
import { useState, useEffect, useCallback } from "react";
import { createGroupApi, createRoleApi } from "@/modules/signin/utils/request";
import type { GroupItem, PermissionGroupItem } from "@/api/generated/auth-client";
import { LockOutlined, SaveOutlined } from "@ant-design/icons";

interface ManagePermissionsModalProps {
  visible: boolean;
  group: GroupItem | null;
  isAdmin: boolean;
  onCancel: () => void;
}

const ManagePermissionsModal = ({ visible, group, isAdmin, onCancel }: ManagePermissionsModalProps) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [allPermissions, setAllPermissions] = useState<PermissionGroupItem[]>([]);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    if (!group) return;
    setLoading(true);
    try {
      const groupApi = createGroupApi();
      const roleApi = createRoleApi();
      
      const [allPermsRes, groupPermsRes] = await Promise.all([
        roleApi.listPermissionGroupsApiAuthserviceRolePermissionGroupsGet(),
        groupApi.getGroupPermissionsApiAuthserviceGroupGroupIdPermissionsGet({
          groupId: group.group_id,
        })
      ]);

      const allPerms = (allPermsRes.data as any).data || allPermsRes.data || [];
      const groupPerms = (groupPermsRes.data as any).data?.permission_groups || groupPermsRes.data?.permission_groups || [];

      setAllPermissions(allPerms);
      setSelectedPermissions(groupPerms);
    } catch (error) {
      console.error("Failed to fetch permissions:", error);
      message.error("获取权限列表失败");
    } finally {
      setLoading(false);
    }
  }, [group]);

  useEffect(() => {
    if (visible && group) {
      fetchData();
    }
  }, [visible, group, fetchData]);

  const handleSave = async () => {
    if (!group) return;
    setSaving(true);
    try {
      const groupApi = createGroupApi();
      await groupApi.setGroupPermissionsApiAuthserviceGroupGroupIdPermissionsPut({
        groupId: group.group_id,
        groupPermissionsBody: { permission_groups: selectedPermissions },
      });
      message.success("保存权限成功");
      onCancel();
    } catch (error) {
      console.error("Save permissions failed:", error);
      message.error("保存权限失败");
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = (code: string) => {
    if (!isAdmin) return;
    setSelectedPermissions(prev => 
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    );
  };

  const columns = [
    {
      title: "模块",
      dataIndex: "module",
      key: "module",
      width: 120,
    },
    {
      title: "操作",
      dataIndex: "action",
      key: "action",
      width: 100,
    },
    {
      title: "编码",
      dataIndex: "code",
      key: "code",
      width: 150,
    },
    {
      title: "描述",
      dataIndex: "description",
      key: "description",
    },
    {
      title: "已启用",
      key: "enabled",
      width: 80,
      render: (_: any, record: PermissionGroupItem) => (
        <Checkbox 
          checked={selectedPermissions.includes(record.code)} 
          onChange={() => handleToggle(record.code)}
          disabled={!isAdmin}
        />
      ),
    },
  ];

  return (
    <Modal
      title={
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <LockOutlined />
          <span>用户组权限：{group?.group_name}</span>
        </div>
      }
      open={visible}
      onCancel={onCancel}
      onOk={handleSave}
      okText="保存"
      cancelText="取消"
      footer={isAdmin ? undefined : null}
      confirmLoading={saving}
      width={800}
      destroyOnHidden
    >
      <Table
        columns={columns}
        dataSource={allPermissions}
        rowKey="code"
        loading={loading}
        size="middle"
        pagination={false}
        scroll={{ y: 400 }}
      />
    </Modal>
  );
};

export default ManagePermissionsModal;
