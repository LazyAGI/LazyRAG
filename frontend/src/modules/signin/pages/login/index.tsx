import { useContext, useEffect, useState } from "react";
import { Button, Form, Input, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import {
  loginByPassword,
  storeLoginSession,
  unwrapLoginResponse,
} from "@/modules/signin/utils/request";
import { FormContext } from "../dashboard";
import { AgentAppsAuth } from "@/components/auth";

interface LoginForm {
  username: string;
  password: string;
}

const hashBase = () =>
  `${window.location.origin}${window.location.pathname || ""}#`;

const Login = () => {
  const form = useContext(FormContext);
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);

  const checkUserLogin = () => {
    try {
      const userInfo = AgentAppsAuth.getUserInfo();
      if (userInfo && userInfo.token) {
        window.location.href = hashBase() + "/agent/chat";
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    document.cookie =
      "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    const postLogoutCleanup =
      sessionStorage.getItem("signin_post_logout_cleanup") ||
      localStorage.getItem("signin_post_logout_cleanup");
    if (postLogoutCleanup === "1") {
      [
        "signin_username",
        "signin_password",
        "signin_login_count",
        "signin_login_tag",
        "signin_sso_url",
        "signin_sso_client_id",
      ].forEach((key) => {
        localStorage.removeItem(key);
        sessionStorage.removeItem(key);
      });
      sessionStorage.removeItem("signin_post_logout_cleanup");
      localStorage.removeItem("signin_post_logout_cleanup");
    }
    checkUserLogin();
    const prefilledUsername = (location.state as { username?: string } | null)
      ?.username;
    if (prefilledUsername) {
      form?.setFieldValue?.("username", prefilledUsername);
    }
  }, [form, location.state]);

  const clearSigninRetryLocalCache = () => {
    [
      "signin_username",
      "signin_password",
      "signin_login_count",
      "signin_login_tag",
      "signin_sso_url",
      "signin_sso_client_id",
    ].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
  };

  const onSubmit = async (value: LoginForm) => {
    setLoading(true);
    try {
      const res = await loginByPassword({
        username: value.username,
        password: value.password,
      });
      const loginData = unwrapLoginResponse(res.data as any);
      await storeLoginSession(loginData, value.username);
      clearSigninRetryLocalCache();
      window.location.href = hashBase() + "/agent/chat";
    } catch (error: any) {
      if (!error?.response && !error?.request) {
        message.error(error?.message || "登录失败，请检查账号密码");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signin-container">
      <div style={{ paddingBottom: '4px' }}>
        <h2 style={{ 
          fontSize: '18px', 
          fontWeight: 600, 
          color: '#1d2129', 
          textAlign: 'center',
          marginBottom: '20px'
        }}>
          欢迎登录
        </h2>
      </div>
      <Form
        className="sign-form"
        autoComplete="off"
        layout="vertical"
        form={form}
        onFinish={onSubmit}
        requiredMark={false}
      >
        <Form.Item
          name="username"
          label="账号"
          rules={[{ required: true, message: "请输入登录账号" }]}
        >
          <Input 
            placeholder="请输入账号" 
            size="large"
          />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[{ required: true, message: "请输入登录密码" }]}
        >
          <Input.Password 
            placeholder="请输入密码" 
            size="large"
          />
        </Form.Item>
        <Form.Item style={{ marginTop: '24px' }}>
          <Button
            block
            type="primary"
            size="large"
            htmlType="submit"
            loading={loading}
          >
            登录
          </Button>
          <div style={{ textAlign: "center", marginTop: "16px", color: '#86909c' }}>
            没有账号？ <a style={{ color: '#1677ff', fontWeight: 500 }} onClick={() => navigate("/register")}>立即注册</a>
          </div>
        </Form.Item>
      </Form>
    </div>
  );
};

export default Login;
