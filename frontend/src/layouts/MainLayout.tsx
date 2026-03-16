import { useEffect, useState } from "react";
import { Button, Form, Input, Layout, Menu, Modal, Popover, message } from "antd";
import type { MenuProps } from "antd";
import {
  SettingOutlined,
  UserOutlined,
  MessageFilled,
  AppstoreOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { UserDetailResponse } from "@/api/generated/auth-client";
import { AgentAppsAuth } from "@/components/auth";
import {
  changeCurrentUserPassword,
  fetchCurrentUserDetail,
  updateCurrentUserProfile,
} from "@/modules/signin/utils/request";
import { validatePassword } from "@/modules/signin/utils/formRules";
import logoImage from "@/public/Lazy.png";
import "./index.scss";

const { Content, Sider } = Layout;

type MenuItem = Required<MenuProps>["items"][number];

const allMenuItems: any[] = [
  {
    key: "agent",
    label: "智能体",
    type: "group",
    children: [
      { key: "/agent/chat", label: "知识问答", icon: <MessageFilled /> },
    ],
  },
  {
    key: "lib",
    label: "资源库",
    type: "group",
    children: [
      { key: "/lib/knowledge", label: "知识库", icon: <AppstoreOutlined /> },
    ],
  },
  {
    key: "system",
    label: "系统管理",
    type: "group",
    children: [
      { key: "/admin/users", label: "用户管理", icon: <UserOutlined />, role: "admin" },
      { key: "/admin/groups", label: "用户组管理", icon: <TeamOutlined /> },
    ],
  },
];

function isAdminRole(role?: string) {
  const normalizedRole = (role || "").trim().toLowerCase();
  return (
    normalizedRole === "admin" ||
    normalizedRole === "system-admin" ||
    normalizedRole === "system_admin" ||
    normalizedRole.endsWith(".admin")
  );
}

interface ProfileFormValues {
  username: string;
  displayName?: string;
  email?: string;
  phone?: string;
  remark?: string; // 添加描述字段
  roleName?: string;
  status?: string;
  currentPassword?: string;
  newPassword?: string;
  confirmPassword?: string;
}

function normalizeFieldValue(value?: string | null) {
  return (value || "").trim();
}

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [profileForm] = Form.useForm<ProfileFormValues>();
  const pathname = location.pathname || "/agent/chat";

  const userInfo = AgentAppsAuth.getUserInfo();
  const isLoggedIn = Boolean(userInfo?.token);
  const canViewSystemMenu = isAdminRole(userInfo?.role);
  const userName = userInfo?.username || "";

  const [selectKeys, setSelectKeys] = useState<string[]>([
    pathname.startsWith("/lib")
      ? "/lib/knowledge"
      : pathname.startsWith("/admin/users") && canViewSystemMenu
      ? "/admin/users"
      : pathname.startsWith("/admin/groups")
      ? "/admin/groups"
      : "/agent/chat",
  ]);

  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileSubmitting, setProfileSubmitting] = useState(false);
  const [profileDetail, setProfileDetail] = useState<UserDetailResponse | null>(
    null,
  );
  const menuItems = allMenuItems
    .map((group) => {
      const filteredChildren = group.children?.filter((child: any) => {
        if (child.role === "admin" && !canViewSystemMenu) return false;
        return true;
      });
      if (filteredChildren?.length > 0) {
        return { ...group, children: filteredChildren };
      }
      return null;
    })
    .filter(Boolean) as MenuItem[];
  const logoSrc =
    (import.meta.env as ImportMetaEnv & { VITE_APP_LOGO?: string })
      .VITE_APP_LOGO || "";

  useEffect(() => {
    let key = "/agent/chat";
    if (pathname.startsWith("/lib")) {
      key = "/lib/knowledge";
    } else if (pathname.startsWith("/admin/users") && canViewSystemMenu) {
      key = "/admin/users";
    } else if (pathname.startsWith("/admin/groups")) {
      key = "/admin/groups";
    }
    setSelectKeys([key]);
  }, [canViewSystemMenu, pathname]);

  useEffect(() => {
    if (pathname.startsWith("/admin/users") && !canViewSystemMenu) {
      navigate("/agent/chat", { replace: true });
    }
  }, [canViewSystemMenu, navigate, pathname]);

  const onMenuClick: MenuProps["onClick"] = (e) => {
    const targetPath = e.key as string;
    if (selectKeys.includes(targetPath)) return;
    setSelectKeys([targetPath]);
    navigate(targetPath);
  };

  const handleLogout = () => {
    AgentAppsAuth.logout(
      window.location.origin + (window.location.pathname || "") + "#/login",
    );
  };

  const handleGoLogin = () => {
    navigate("/login");
  };

  const currentPasswordRule = ({ getFieldValue }: any) => ({
    validator(_: any, value: string) {
      const newPassword = getFieldValue("newPassword");
      const confirmPassword = getFieldValue("confirmPassword");
      if (!newPassword && !confirmPassword && !value) {
        return Promise.resolve();
      }
      if (!value) {
        return Promise.reject(new Error("请输入当前密码"));
      }
      return Promise.resolve();
    },
  });

  const passwordRequiredRule = ({ getFieldValue }: any) => ({
    validator(_: any, value: string) {
      const currentPassword = getFieldValue("currentPassword");
      const confirmPassword = getFieldValue("confirmPassword");
      if (!currentPassword && !confirmPassword && !value) {
        return Promise.resolve();
      }
      if (!value) {
        return Promise.reject(new Error("请输入新密码"));
      }
      return validatePassword(value);
    },
  });

  const confirmPasswordRule = ({ getFieldValue }: any) => ({
    validator(_: any, value: string) {
      const currentPassword = getFieldValue("currentPassword");
      const newPassword = getFieldValue("newPassword");
      if (!currentPassword && !newPassword && !value) {
        return Promise.resolve();
      }
      if (!value) {
        return Promise.reject(new Error("请确认新密码"));
      }
      if (value !== newPassword) {
        return Promise.reject(new Error("两次输入的密码不一致"));
      }
      return Promise.resolve();
    },
  });

  const applyProfileToForm = (detail: UserDetailResponse) => {
    profileForm.setFieldsValue({
      username: detail.username,
      displayName: detail.display_name || "",
      email: detail.email || "",
      phone: detail.phone || "",
      remark: (detail as any).remark || "", // 处理可能缺失的 remark
      roleName: detail.role_name || "",
      status: detail.status || "",
      currentPassword: "",
      newPassword: "",
      confirmPassword: "",
    });
  };

  const refreshCurrentProfile = async () => {
    const detail = await fetchCurrentUserDetail();
    setProfileDetail(detail);
    applyProfileToForm(detail);
    return detail;
  };

  const handleOpenProfile = async () => {
    setProfileModalOpen(true);
    setProfileLoading(true);
    try {
      await refreshCurrentProfile();
    } catch {
      setProfileModalOpen(false);
    } finally {
      setProfileLoading(false);
    }
  };

  const handleCloseProfile = () => {
    setProfileModalOpen(false);
    setProfileLoading(false);
    setProfileSubmitting(false);
    setProfileDetail(null);
    profileForm.resetFields();
  };

  const handleProfileSubmit = async () => {
    try {
      const values = await profileForm.validateFields();
      if (!profileDetail?.user_id) {
        message.error("未获取到当前用户信息");
        return;
      }

      const payload: {
        display_name?: string;
        email?: string;
        phone?: string;
        remark?: string;
      } = {};
      const nextDisplayName = normalizeFieldValue(values.displayName);
      const nextEmail = normalizeFieldValue(values.email);
      const nextPhone = normalizeFieldValue(values.phone);
      const nextRemark = normalizeFieldValue(values.remark);
      const currentPassword = values.currentPassword || "";
      const newPassword = values.newPassword || "";

      if (
        nextDisplayName !== normalizeFieldValue(profileDetail.display_name || "")
      ) {
        payload.display_name = nextDisplayName;
      }
      if (nextEmail !== normalizeFieldValue(profileDetail.email || "")) {
        payload.email = nextEmail;
      }
      if (nextPhone !== normalizeFieldValue(profileDetail.phone || "")) {
        payload.phone = nextPhone;
      }
      if (nextRemark !== normalizeFieldValue((profileDetail as any).remark || "")) {
        payload.remark = nextRemark;
      }

      const shouldUpdateProfile = Object.keys(payload).length > 0;
      const shouldUpdatePassword = Boolean(currentPassword || newPassword);

      if (!shouldUpdateProfile && !shouldUpdatePassword) {
        message.info("未检测到需要保存的变更");
        return;
      }

      setProfileSubmitting(true);

      if (shouldUpdateProfile) {
        await updateCurrentUserProfile(payload);
      }

      if (shouldUpdatePassword) {
        await changeCurrentUserPassword(currentPassword, newPassword);
      }

      await refreshCurrentProfile();
      message.success("账号信息已更新");
      handleCloseProfile();
    } catch (error: any) {
      if (!error?.errorFields) {
        console.error("Failed to update current user profile:", error);
      }
    } finally {
      setProfileSubmitting(false);
    }
  };

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Layout hasSider className="main-layout">
      <Sider width={200} className="sider-bar-style">
        <div className="sider-inner">
          <div className="img-box">
            {logoSrc ? (
              <img src={logoSrc} alt="logo" />
            ) : (
              <img
                src={logoImage}
                alt="logo"
                style={{ width: 40, height: "auto" }}
              />
            )}
          </div>
          <Menu
            onClick={onMenuClick}
            selectedKeys={selectKeys}
            items={menuItems}
            mode="inline"
            className="sider-menu"
            style={{ border: "none" }}
          />
          <div className="sider-bar-bottom">
            <div className="bottom-item">
              <SettingOutlined className="bottom-icon" />
              <Popover
                content={
                  <div className="settings-popover">
                    {isLoggedIn ? (
                      <Button type="text" onClick={handleLogout}>
                        退出登录
                      </Button>
                    ) : (
                      <Button type="text" onClick={handleGoLogin}>
                        前往登录
                      </Button>
                    )}
                  </div>
                }
                arrow={false}
                placement="top"
              >
                <span className="bottom-text">设置</span>
              </Popover>
            </div>
            {userName && (
              <div
                className="bottom-item user-item"
                onClick={handleOpenProfile}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleOpenProfile();
                  }
                }}
              >
                <UserOutlined className="bottom-icon" />
                <span className="bottom-text">{userName}</span>
              </div>
            )}
          </div>
        </div>
      </Sider>
      <Layout className="main-layout-content">
        <Content className="main-layout-body">
          <div className="sub-app-container">
            <Outlet />
          </div>
        </Content>
      </Layout>
      <Modal
        title="个人信息"
        open={profileModalOpen}
        onCancel={handleCloseProfile}
        onOk={handleProfileSubmit}
        confirmLoading={profileSubmitting}
        destroyOnHidden
        maskClosable={false}
      >
        <Form
          form={profileForm}
          layout="vertical"
          disabled={profileLoading || profileSubmitting}
        >
          <Form.Item name="username" label="用户名">
            <Input disabled />
          </Form.Item>
          <Form.Item name="displayName" label="昵称">
            <Input placeholder="请输入昵称" />
          </Form.Item>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[{ type: "email", message: "请输入有效的邮箱格式" }]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item name="remark" label="描述">
            <Input.TextArea placeholder="请输入描述" />
          </Form.Item>
          <Form.Item name="roleName" label="角色">
            <Input disabled />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Input disabled />
          </Form.Item>
          <Form.Item
            name="currentPassword"
            label="当前密码"
            rules={[currentPasswordRule]}
          >
            <Input.Password placeholder="如需修改密码，请输入当前密码" />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label="新密码"
            dependencies={["currentPassword", "confirmPassword"]}
            rules={[passwordRequiredRule]}
          >
            <Input.Password placeholder="不修改密码可留空" />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label="确认新密码"
            dependencies={["currentPassword", "newPassword"]}
            rules={[confirmPasswordRule]}
          >
            <Input.Password placeholder="请再次输入新密码" />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  );
}
