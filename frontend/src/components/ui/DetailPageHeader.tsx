import { Breadcrumb, type BreadcrumbProps, Button, Typography } from "antd";
import { LeftOutlined } from "@ant-design/icons";
import { useStyles } from "./useStyles";

const headerCss = `
.common-detail-page-header {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-page-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.detail-title { font-size: 20px; font-weight: 600; }
.title-extra, .detail-page-description { font-size: 14px; color: #666; }
.settings-menu { display: flex; align-items: center; gap: 4px; }
.extra-content { display: flex; flex-wrap: wrap; gap: 8px 24px; }
.extra-content-item { display: flex; align-items: center; gap: 8px; }
.extra-content-label { font-size: 12px; color: #666; }
.extra-content-value { font-size: 12px; }
`;

interface ContentItem {
  label: React.ReactNode | string;
  value: React.ReactNode | string;
  hidden?: boolean;
}

export interface DetailPageHeaderProps {
  className?: string;
  breadcrumbs?: BreadcrumbProps["items"];
  title?: React.ReactNode | string;
  titleExtra?: React.ReactNode | string;
  description?: React.ReactNode | string;
  showBackButton?: boolean;
  settingsMenu?: React.ReactNode;
  extraContent?: ContentItem[];
  extraSplitter?: string;
  onBack?: () => void;
}

export default function DetailPageHeader({
  className = "",
  breadcrumbs,
  title,
  titleExtra,
  description,
  showBackButton = true,
  settingsMenu,
  extraContent,
  extraSplitter = "",
  onBack,
}: DetailPageHeaderProps) {
  useStyles("detail-page-header-styles", headerCss);

  return (
    <div className={`common-detail-page-header ${className}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumb items={breadcrumbs} />
      )}
      <div className="detail-page-title">
        {showBackButton && (
          <Button
            type="primary"
            ghost
            icon={<LeftOutlined />}
            onClick={() => (onBack ? onBack() : window.history.back())}
          />
        )}
        <span className="detail-title">{title}</span>
        {settingsMenu && <div className="settings-menu">{settingsMenu}</div>}
        {titleExtra && <div className="title-extra">{titleExtra}</div>}
      </div>
      {extraContent && extraContent.length > 0 && (
        <div className="extra-content">
          {extraContent
            .filter((item) => !item.hidden)
            .map((item, index) => (
              <div key={index} className="extra-content-item">
                <span className="extra-content-label">
                  {item.label}
                  {extraSplitter}
                </span>
                <span className="extra-content-value">{item.value}</span>
              </div>
            ))}
        </div>
      )}
      {description && (
        <div className="detail-page-description">
          <Typography.Paragraph
            ellipsis={{ rows: 1, expandable: false }}
            style={{ marginBottom: 0 }}
          >
            {description}
          </Typography.Paragraph>
        </div>
      )}
    </div>
  );
}
