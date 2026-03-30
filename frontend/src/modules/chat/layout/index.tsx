import { ReactNode } from "react";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

const Layout = ({
  token = {},
  children,
}: {
  token?: object;
  children?: ReactNode;
}) => {
  return (
    <ConfigProvider theme={{ token }} locale={zhCN}>
      {children}
    </ConfigProvider>
  );
};

export default Layout;
