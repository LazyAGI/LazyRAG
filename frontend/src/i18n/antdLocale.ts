import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import type { Locale } from "antd/es/locale";

export function getAntdLocale(language?: string): Locale {
  if (language?.toLowerCase().startsWith("en")) {
    return enUS;
  }

  return zhCN;
}
