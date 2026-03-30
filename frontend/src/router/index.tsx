import { Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import MainLayout from "@/layouts/MainLayout";
import SigninLogin from "@/modules/signin/pages/login";
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

export default function AppRouter() {
  return (
    <ConfigProvider locale={zhCN}>
      <Routes>
        <Route path="/login" element={<SigninDashboard />}>
          <Route index element={<SigninLogin />} />
        </Route>
        <Route path="/register" element={<SigninDashboard />}>
          <Route index element={<SigninRegister />} />
        </Route>
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
          <Route index element={<Navigate to="users" replace />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="groups" element={<GroupManagement />} />
          <Route path="groups/:id" element={<GroupDetail />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ConfigProvider>
  );
}
