import { Breadcrumb, type BreadcrumbProps, Button, Tooltip } from "antd";
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
  min-width: 0;
}
.detail-title {
  font-size: 20px;
  font-weight: 600;
  min-width: 0;
  flex: 1 1 auto;
}
.detail-title-text,
.detail-page-description-text,
.detail-breadcrumb-text {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.detail-title-text {
  max-width: 100%;
}
.detail-breadcrumb-text {
  max-width: min(60vw, 960px);
}
.title-extra, .detail-page-description { font-size: 14px; color: #666; }
.detail-page-description-text {
  max-width: 100%;
}
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
  const normalizedBreadcrumbs = breadcrumbs?.map((item) => {
    if (!item || typeof item.title !== "string" || !item.title.trim()) {
      return item;
    }
    const text = item.title;
    return {
      ...item,
      title: (
        <Tooltip title={text} placement="topLeft">
          <span className="detail-breadcrumb-text">{text}</span>
        </Tooltip>
      ),
    };
  });

  const resolvedTitle =
    typeof title === "string" ? (
      <Tooltip title={title} placement="topLeft">
        <span className="detail-title-text">{title}</span>
      </Tooltip>
    ) : (
      title
    );

  const resolvedDescription =
    typeof description === "string" ? (
      <Tooltip title={description} placement="topLeft">
        <span className="detail-page-description-text">{description}</span>
      </Tooltip>
    ) : (
      description
    );

  return (
    <div className={`common-detail-page-header ${className}`}>
      {normalizedBreadcrumbs && normalizedBreadcrumbs.length > 0 && (
        <Breadcrumb items={normalizedBreadcrumbs} />
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
        <span className="detail-title">{resolvedTitle}</span>
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
      {description && <div className="detail-page-description">{resolvedDescription}</div>}
    </div>
  );
}
