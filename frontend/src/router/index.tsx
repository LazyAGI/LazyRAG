import { Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider } from "antd";
import { useTranslation } from "react-i18next";
import MainLayout from "@/layouts/MainLayout";
import SigninLogin from "@/modules/signin/pages/login";
import FeishuCallback from "@/modules/signin/pages/feishuCallback";
import SigninRegister from "@/modules/signin/pages/register";
import SigninDashboard from "@/modules/signin/pages/dashboard";
import LoginTransition from "@/modules/signin/pages/loginTransition";
import ChatApp from "@/modules/chat/ChatApp";
import Home from "@/modules/chat/pages/home";
import KnowledgeApp from "@/modules/knowledge/KnowledgeApp";
import KnowledgeList from "@/modules/knowledge/pages/list";
import KnowledgeAuth from "@/modules/knowledge/pages/auth";
import KnowledgeDetail from "@/modules/knowledge/pages/detail";
import Knowledge from "@/modules/knowledge/pages/knowledge";
import AdminLayout from "@/modules/admin/AdminLayout";
import UserManagement from "@/modules/admin/pages/user";
import GroupManagement from "@/modules/admin/pages/group";
import GroupDetail from "@/modules/admin/pages/group/detail.tsx";
import DataSourceManagement from "@/modules/admin/pages/dataSource";
import DataSourceDetail from "@/modules/admin/pages/dataSource/detail";
import DataSourceFeishuCallback from "@/modules/admin/pages/dataSource/feishuCallback";
import MemoryManagement from "@/modules/admin/pages/memory";
import { getAntdLocale } from "@/i18n/antdLocale";

export default function AppRouter() {
  const { i18n } = useTranslation();

  return (
    <ConfigProvider locale={getAntdLocale(i18n.resolvedLanguage || i18n.language)}>
      <Routes>
        <Route path="/login" element={<SigninDashboard />}>
          <Route index element={<SigninLogin />} />
          <Route path="feishu/callback" element={<FeishuCallback />} />
        </Route>
        <Route path="/register" element={<SigninDashboard />}>
          <Route index element={<SigninRegister />} />
        </Route>
        <Route
          path="/oauth/feishu/data-source/callback"
          element={<DataSourceFeishuCallback />}
        />
        <Route path="/loginTransition" element={<LoginTransition />} />
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/agent/chat" replace />} />
          <Route path="agent/chat" element={<ChatApp />}>
            <Route index element={<Navigate to="home" replace />} />
            <Route path="home" element={<Home />} />
          </Route>
          <Route path="lib/knowledge" element={<KnowledgeApp />}>
            <Route index element={<Navigate to="list" replace />} />
            <Route path="list" element={<KnowledgeList />} />
            <Route path="auth/:id" element={<KnowledgeAuth />} />
            <Route path="detail/:id" element={<KnowledgeDetail />} />
            <Route
              path="knowledge/:knowledgeBaseId/:knowledgeId"
              element={<Knowledge />}
            />
          </Route>
        </Route>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="groups" replace />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="groups" element={<GroupManagement />} />
          <Route path="groups/:id" element={<GroupDetail />} />
          <Route path="data-sources" element={<DataSourceManagement />} />
          <Route path="data-sources/:id" element={<DataSourceDetail />} />
          <Route path="memory-management" element={<MemoryManagement />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ConfigProvider>
  );
}
