import { Tooltip } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";

function RiskTip() {
  return (
    <Tooltip
      title={
        <span>
          为了保障您的信息安全,请勿上传您的敏感个人信息(如您的密码等信息)和您的敏感资产信息(如关键源代码、签名私钥、调试安装包、业务日志等信息),且您需自行承担由此产生的信息泄露等安全风险。
        </span>
      }
    >
      <InfoCircleOutlined />
    </Tooltip>
  );
}

export default RiskTip;
