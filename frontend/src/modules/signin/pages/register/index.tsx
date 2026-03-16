import { useState } from "react";
import { Button, Form, Input, message } from "antd";
import { useNavigate } from "react-router-dom";
import { registerByPassword } from "@/modules/signin/utils/request";
import {
  passwordRules,
  usernameRules,
} from "@/modules/signin/utils/formRules";

interface RegisterFormValues {
  username: string;
  email?: string;
  password: string;
  confirmPassword: string;
  captcha: string;
}

const Register = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: RegisterFormValues) => {
    setLoading(true);
    try {
      await registerByPassword({
        username: values.username,
        password: values.password,
        confirm_password: values.confirmPassword,
        email: values.email || undefined,
        captcha: values.captcha, // 添加验证码
      } as any);
      message.success("注册成功，请登录");
      navigate("/login", { state: { username: values.username } });
    } catch (error: any) {
      if (!error?.response && !error?.request) {
        message.error(error?.message || "注册失败，请重试");
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
          新用户注册
        </h2>
      </div>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        autoComplete="off"
        requiredMark={false}
        style={{ marginBottom: 0 }}
      >
        <Form.Item
          name="username"
          label="用户名"
          rules={usernameRules}
        >
          <Input placeholder="请输入用户名" />
        </Form.Item>

        <Form.Item
          name="email"
          label="电子邮箱"
          rules={[
            { type: "email", message: "邮箱格式不正确" },
          ]}
        >
          <Input placeholder="example@email.com（选填）" />
        </Form.Item>

        <Form.Item
          name="password"
          label="设置密码"
          rules={passwordRules}
        >
          <Input.Password 
            placeholder="请输入密码" 
          />
        </Form.Item>

        <Form.Item
          name="confirmPassword"
          label="确认密码"
          dependencies={['password']}
          rules={[
            { required: true, message: "请再次输入密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error('两次输入的密码不一致'));
              },
            }),
          ]}
        >
          <Input.Password 
            placeholder="请再次输入密码" 
          />
        </Form.Item>

        <Form.Item
          name="captcha"
          label="验证码"
          rules={[{ required: true, message: "请输入验证码" }]}
        >
          <div style={{ display: 'flex', gap: '8px' }}>
            <Input placeholder="请输入验证码" style={{ flex: 1 }} />
            <Button style={{ width: '120px' }}>获取验证码</Button>
          </div>
        </Form.Item>

        <Form.Item style={{ marginTop: '16px', marginBottom: 0 }}>
          <Button type="primary" htmlType="submit" block loading={loading}>
            立即注册
          </Button>
          <div style={{ textAlign: 'center', marginTop: '12px', color: '#86909c', fontSize: '13px' }}>
            已有账号？ <a style={{ color: '#1677ff', fontWeight: 500 }} onClick={() => navigate("/login")}>返回登录</a>
          </div>
        </Form.Item>
      </Form>
    </div>
  );
};

export default Register;
