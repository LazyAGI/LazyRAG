import { useEffect, useState } from "react";
import { Button, Form, Input, Layout, Menu, Modal, Popover, message } from "antd";
import type { MenuProps } from "antd";
import {
  CodeOutlined,
  SettingOutlined,
  UserOutlined,
  MessageFilled,
  AppstoreOutlined,
  TeamOutlined,
  GlobalOutlined,
  DatabaseOutlined,
  ApiOutlined,
  LeftOutlined,
  RightOutlined,
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
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import {
  isDeveloperModeActive,
  setDeveloperModeActive,
} from "@/utils/developerMode";
import "./index.scss";

const { Content, Sider } = Layout;
const MAINLAND_CHINA_PHONE_REGEX = /^1[3-9]\d{9}$/;
const MAIN_MENU_COLLAPSED_STORAGE_KEY = "lazyrag:main-menu-collapsed";

function readStoredMainMenuCollapsed() {
  try {
    return localStorage.getItem(MAIN_MENU_COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

type MenuItem = Required<MenuProps>["items"][number];

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
  remark?: string;
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
  const { t } = useTranslation();
  const [profileForm] = Form.useForm<ProfileFormValues>();

  const userInfo = AgentAppsAuth.getUserInfo();
  const isLoggedIn = Boolean(userInfo?.token);
  const userName = userInfo?.username || "";
  const isAdminUser = isAdminRole(userInfo?.role);

  const [selectKeys, setSelectKeys] = useState<string[]>([]);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileSubmitting, setProfileSubmitting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isMenuCollapsed, setIsMenuCollapsed] = useState(readStoredMainMenuCollapsed);
  const [developerActive, setDeveloperActive] = useState(isDeveloperModeActive);
  const [profileDetail, setProfileDetail] = useState<UserDetailResponse | null>(null);
  const aiEvolutionMenuChildren: MenuItem[] = [
    ...(isAdminUser && developerActive
      ? [{ key: "/self-evolution", label: t("layout.selfEvolution"), icon: <CodeOutlined /> }]
      : []),
    { key: "/memory-management", label: t("layout.memoryManagement"), icon: <AppstoreOutlined /> },
  ];
  const allMenuItems: MenuItem[] = [
    {
      key: "agent",
      label: t("layout.agent"),
      type: "group",
      children: [
        { key: "/agent/chat", label: t("layout.knowledgeQA"), icon: <MessageFilled /> },
      ],
    },
    {
      key: "lib",
      label: t("layout.resourceLib"),
      type: "group",
      children: [
        { key: "/lib/knowledge", label: t("layout.knowledgeBase"), icon: <AppstoreOutlined /> },
        { key: "/data-sources", label: t("layout.dataSourceManagement"), icon: <DatabaseOutlined /> },
        { key: "/model-providers", label: t("layout.modelProviderManagement"), icon: <ApiOutlined /> },
      ],
    },
    {
      key: "ai-evolution",
      label: t("layout.aiEvolution"),
      type: "group",
      children: aiEvolutionMenuChildren,
    },
  ];

  const pathname = location.pathname || "/agent/chat";
  const menuItems = allMenuItems;

  const settingsMenuItems = [
    {
      key: "/admin",
      label: t("layout.systemManagement"),
      icon: <TeamOutlined className="settings-popover-icon" />,
    },
    {
      key: "developer-toggle",
      label: t("layout.developer"),
      icon: <CodeOutlined className="settings-popover-icon" />,
    },
  ];
  const logoSrc =
    (import.meta.env as ImportMetaEnv & { VITE_APP_LOGO?: string })
      .VITE_APP_LOGO || "";

  useEffect(() => {
    setDeveloperActive(isDeveloperModeActive());
  }, []);

  useEffect(() => {
    let key = "/agent/chat";
    if (pathname.startsWith("/lib")) {
      key = "/lib/knowledge";
    } else if (pathname.startsWith("/data-sources")) {
      key = "/data-sources";
    } else if (pathname.startsWith("/model-providers")) {
      key = "/model-providers";
    } else if (pathname.startsWith("/memory-management")) {
      key = "/memory-management";
    } else if (pathname.startsWith("/self-evolution")) {
      key = "/self-evolution";
    }
    setSelectKeys([key]);
  }, [pathname]);

  useEffect(() => {
    if (pathname.startsWith("/self-evolution") && (!isAdminUser || !developerActive)) {
      navigate("/agent/chat", { replace: true });
    }
  }, [pathname, isAdminUser, developerActive, navigate]);

  useEffect(() => {
    setIsMenuCollapsed(readStoredMainMenuCollapsed());
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(MAIN_MENU_COLLAPSED_STORAGE_KEY, isMenuCollapsed ? "1" : "0");
    } catch {
      // ignore persistence errors
    }
  }, [isMenuCollapsed]);

  const onMenuClick: MenuProps["onClick"] = (e) => {
    const targetPath = e.key as string;
    if (selectKeys.includes(targetPath)) return;
    setSelectKeys([targetPath]);
    navigate(targetPath);
  };

  const toggleMenu = () => {
    setIsMenuCollapsed((prev) => !prev);
  };

  const handleSettingsNavigate = (targetPath: string) => {
    if (targetPath === "developer-toggle") {
      if (developerActive) {
        setDeveloperActive(false);
        setDeveloperModeActive(false);
        message.success(t("admin.developerDeactivated"));
        if (pathname.startsWith("/self-evolution")) {
          navigate("/agent/chat");
        }
        return;
      }

      setDeveloperActive(true);
      setDeveloperModeActive(true);
      message.success(t("admin.developerActivated"));
      return;
    }

    setSettingsOpen(false);
    navigate(targetPath);
  };

  const handleLogout = () => {
    AgentAppsAuth.logout(
      `${window.location.origin}${window.BASENAME || ""}/login`,
    );
  };

  const handleGoLogin = () => {
    setSettingsOpen(false);
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
        return Promise.reject(new Error(t("profile.pleaseInputCurrentPasswordRequired")));
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
        return Promise.reject(new Error(t("profile.pleaseInputNewPasswordRequired")));
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
        return Promise.reject(new Error(t("profile.pleaseConfirmNewPassword")));
      }
      if (value !== newPassword) {
        return Promise.reject(new Error(t("profile.passwordNotMatch")));
      }
      return Promise.resolve();
    },
  });

  const phoneRule = {
    validator(_: any, value?: string) {
      const phone = normalizeFieldValue(value);
      if (!phone || MAINLAND_CHINA_PHONE_REGEX.test(phone)) {
        return Promise.resolve();
      }
      return Promise.reject(new Error(t("profile.invalidPhone")));
    },
  };

  const clearPasswordFields = () => {
    profileForm.setFieldsValue({
      currentPassword: "",
      newPassword: "",
      confirmPassword: "",
    });
  };

  const schedulePasswordFieldClear = () => {
    window.setTimeout(() => {
      clearPasswordFields();
    }, 0);
    window.setTimeout(() => {
      clearPasswordFields();
    }, 300);
  };

  const applyProfileToForm = (detail: UserDetailResponse) => {
    profileForm.setFieldsValue({
      username: detail.username,
      displayName: detail.display_name || "",
      email: detail.email || "",
      phone: detail.phone || "",
      remark: (detail as any).remark || "",
      roleName: detail.role_name || "",
      status: detail.status || "",
    });
    clearPasswordFields();
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
        message.error(t("profile.noUserInfo"));
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
      message.info(t("profile.noChanges"));
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
      message.success(t("profile.updateSuccess"));
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
      <Sider
        width={232}
        collapsedWidth={72}
        collapsible
        trigger={null}
        collapsed={isMenuCollapsed}
        className={`sider-bar-style${isMenuCollapsed ? " is-collapsed" : ""}`}
      >
        <div className="sider-inner">
          <div className="img-box">
            {logoSrc ? (
              <img src={logoSrc} alt="logo" />
            ) : (
              <img src={logoImage} alt="logo" />
            )}
          </div>
          <div className="sider-top-action">
            <button
              type="button"
              className="sider-inline-toggle"
              onClick={toggleMenu}
              aria-label={isMenuCollapsed ? "展开菜单" : "收起菜单"}
              title={isMenuCollapsed ? "展开菜单" : "收起菜单"}
            >
              {isMenuCollapsed ? <RightOutlined /> : <LeftOutlined />}
              {!isMenuCollapsed && <span className="sider-inline-toggle-text">收起导航</span>}
            </button>
          </div>
          <Menu
            onClick={onMenuClick}
            selectedKeys={selectKeys}
            items={menuItems}
            mode="inline"
            inlineCollapsed={isMenuCollapsed}
            className="sider-menu"
            style={{ border: "none" }}
          />
          <div className="sider-bar-bottom">
            <div className="bottom-item language-item">
              <GlobalOutlined className="bottom-icon" />
              {!isMenuCollapsed && <LanguageSwitcher />}
            </div>
            <Popover
              content={
                <div className="settings-popover">
                  {settingsMenuItems.map((item) => (
                    <Button
                      key={item.key}
                      type="text"
                      className={`settings-popover-button${
                        item.key === "developer-toggle" && developerActive ? " is-active" : ""
                      }`}
                      onClick={() => handleSettingsNavigate(item.key)}
                    >
                      {item.icon}
                      <span>{item.label}</span>
                      {item.key === "developer-toggle" && developerActive && (
                        <span className="settings-active-badge">{t("admin.developerActiveTag")}</span>
                      )}
                    </Button>
                  ))}
                  {isLoggedIn ? (
                    <Button
                      type="text"
                      className="settings-popover-button"
                      onClick={handleLogout}
                    >
                      <span>{t("layout.logout")}</span>
                    </Button>
                  ) : (
                    <Button
                      type="text"
                      className="settings-popover-button"
                      onClick={handleGoLogin}
                    >
                      <span>{t("layout.goLogin")}</span>
                    </Button>
                  )}
                </div>
              }
              arrow={false}
              placement="top"
              trigger="click"
              open={settingsOpen}
              onOpenChange={setSettingsOpen}
            >
              <div
                className="bottom-item settings-trigger"
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSettingsOpen((open) => !open);
                  }
                }}
              >
                <SettingOutlined className="bottom-icon" />
                {!isMenuCollapsed && <span className="bottom-text">{t("layout.settings")}</span>}
              </div>
            </Popover>
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
                {!isMenuCollapsed && <span className="bottom-text">{userName}</span>}
              </div>
            )}
          </div>
        </div>
      </Sider>
      <Layout className="main-layout-content">
        <Content className="main-layout-body">
          <div className="sub-app-container">
            <Outlet
              context={{
                isMenuCollapsed,
                toggleMenu,
              }}
            />
          </div>
        </Content>
      </Layout>
      <Modal
        title={t("profile.title")}
        open={profileModalOpen}
        onCancel={handleCloseProfile}
        onOk={handleProfileSubmit}
        confirmLoading={profileSubmitting}
        destroyOnHidden
        maskClosable={false}
        afterOpenChange={(open) => {
          if (open) {
            schedulePasswordFieldClear();
          }
        }}
      >
        <Form
          form={profileForm}
          layout="vertical"
          disabled={profileLoading || profileSubmitting}
          autoComplete="off"
        >
          <Form.Item name="username" label={t("profile.username")}>
            <Input disabled autoComplete="username" />
          </Form.Item>
          <Form.Item name="displayName" label={t("profile.nickname")}>
            <Input placeholder={t("profile.pleaseInputNickname")} autoComplete="nickname" />
          </Form.Item>
          <Form.Item
            name="email"
            label={t("profile.email")}
            rules={[{ type: "email", message: t("profile.invalidEmail") }]}
          >
            <Input placeholder={t("profile.pleaseInputEmail")} autoComplete="email" />
          </Form.Item>
          <Form.Item
            name="phone"
            label={t("profile.phone")}
            rules={[phoneRule]}
          >
            <Input
              placeholder={t("profile.pleaseInputPhone")}
              autoComplete="tel"
              inputMode="numeric"
              maxLength={11}
            />
          </Form.Item>
          <Form.Item name="remark" label={t("profile.description")}>
            <Input.TextArea placeholder={t("profile.pleaseInputDescription")} />
          </Form.Item>
          <Form.Item name="roleName" label={t("profile.role")}>
            <Input disabled />
          </Form.Item>
          <Form.Item name="status" label={t("profile.status")}>
            <Input disabled />
          </Form.Item>
          <Form.Item
            name="currentPassword"
            label={t("profile.currentPassword")}
            rules={[currentPasswordRule]}
          >
            <Input.Password
              placeholder={t("profile.pleaseInputCurrentPassword")}
              autoComplete="new-password"
              name="profile-current-password"
            />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label={t("profile.newPassword")}
            dependencies={["currentPassword", "confirmPassword"]}
            rules={[passwordRequiredRule]}
          >
            <Input.Password
              placeholder={t("profile.pleaseInputNewPassword")}
              autoComplete="new-password"
              name="profile-new-password"
            />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label={t("profile.confirmNewPassword")}
            dependencies={["currentPassword", "newPassword"]}
            rules={[confirmPasswordRule]}
          >
            <Input.Password
              placeholder={t("profile.pleaseInputConfirmPassword")}
              autoComplete="new-password"
              name="profile-confirm-password"
            />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  );
}
