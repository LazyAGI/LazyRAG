import { ReactNode } from "react";
import zhCN from "antd/locale/zh_CN";
import { ConfigProvider } from "antd";
import AppRouter from "../router";

const Layout = ({
  token = {},
  children,
}: {
  token?: object;
  children?: ReactNode;
}) => {
  return (
    <ConfigProvider theme={{ token }} locale={zhCN}>
      <div className="micro-knowledge-page">
        {children != null ? children : <AppRouter />}
      </div>
    </ConfigProvider>
  );
};

export default Layout;
