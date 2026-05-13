import { ReactNode } from "react";
import { ConfigProvider } from "antd";
import { useTranslation } from "react-i18next";
import { getAntdLocale } from "@/i18n/antdLocale";

const Layout = ({
  token = {},
  children,
}: {
  token?: object;
  children?: ReactNode;
}) => {
  const { i18n } = useTranslation();

  return (
    <ConfigProvider
      theme={{ token }}
      locale={getAntdLocale(i18n.resolvedLanguage || i18n.language)}
    >
      <div className="micro-knowledge-page">{children}</div>
    </ConfigProvider>
  );
};

export default Layout;
