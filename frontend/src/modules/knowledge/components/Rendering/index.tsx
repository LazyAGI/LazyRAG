import { LoadingOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
const Rendering = ({ text }: { text?: string }) => {
  const { t } = useTranslation();
  const displayText = text || t("knowledge.dataLoading");
  return (
    <div className="flex h-full w-full items-center justify-center">
      <LoadingOutlined style={{ color: "var(--color-primary)" }} />
      <span className="ml-2 text-[var(--color-primary)]">{displayText}</span>
    </div>
  );
};

export default Rendering;
