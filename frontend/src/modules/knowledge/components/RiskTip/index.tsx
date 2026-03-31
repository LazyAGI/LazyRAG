import { Tooltip } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";

function RiskTip() {
  const { t } = useTranslation();
  return (
    <Tooltip
      title={<span>{t("knowledge.uploadSecurityRiskTip")}</span>}
    >
      <InfoCircleOutlined />
    </Tooltip>
  );
}

export default RiskTip;
