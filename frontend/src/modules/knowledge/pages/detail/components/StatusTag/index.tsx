import { Tooltip } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import { CSSProperties, ReactNode } from "react";

import { STATUS_COLORS } from "@/modules/knowledge/constants/common";
import "./index.scss";

interface IProps {
  statusConfig?: {
    title: ReactNode;
    color: string; // rgba
    background?: string;
  };
  tips?: {
    show: boolean;
    content?: ReactNode;
    icon?: ReactNode;
  };
  style?: CSSProperties;
}

const StatusTag = (props: IProps) => {
  const { statusConfig, tips, style } = props;
  const {
    title,
    color = STATUS_COLORS.offline,
    background,
  } = statusConfig || {};

  if (!title) {
    return null;
  }

  const changeRgbaAlpha = (rgbaStr: string, newAlpha: number) => {
    const matchNumber = rgbaStr?.match(/\d+/g);
    if (matchNumber?.length !== 4) {
      return "";
    }
    matchNumber[3] = `${newAlpha}`;
    return `rgba(${matchNumber?.join(", ")})`;
  };

  return (
    <div className="statusTagWrap" style={style}>
      <span
        className="statusTag"
        style={{
          color,
          background: background || changeRgbaAlpha(color, 0.1),
        }}
      >
        {title}
      </span>
      {tips?.show && (
        <span style={{ marginLeft: 4, lineHeight: 1 }}>
          <Tooltip
            title={tips.content || " "}
            overlayInnerStyle={{
              maxWidth: 400,
              maxHeight: 300,
              overflow: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {tips.icon || (
              <InfoCircleOutlined
                style={{ fontSize: 18, color: "var(--text-description)" }}
              />
            )}
          </Tooltip>
        </span>
      )}
    </div>
  );
};

export default StatusTag;
