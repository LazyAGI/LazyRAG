import { ReactNode } from "react";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

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
      {children != null ? children : <AppRouter />}
    </ConfigProvider>
  );
};

export default Layout;
