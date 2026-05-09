import { Button, Space, Tag } from "antd";
import RouteLoading from "../../components/RouteLoading";
import { useMemoryManagementOutletContext } from "../../context";

export default function MemoryGlossaryDetailPage() {
  const {
    t,
    glossaryRouteItemId,
    glossaryDetailTarget,
    glossaryDetailExists,
    closeGlossaryDetail,
    openModal,
    glossarySourceColorMap,
    glossarySourceLabelMap,
  } = useMemoryManagementOutletContext();

  if (glossaryRouteItemId && !glossaryDetailTarget) {
    return <RouteLoading title={t("admin.memoryGlossaryDetailTitle")} />;
  }

  if (!glossaryDetailTarget) {
    return null;
  }

  return (
    <div className="memory-glossary-detail-layout">
      <div className="memory-page-header">
        <div>
          <h2 className="admin-page-title">{t("admin.memoryGlossaryDetailTitle")}</h2>
          <p className="memory-page-subtitle">{glossaryDetailTarget.term}</p>
        </div>
        <Space>
          <Button onClick={closeGlossaryDetail}>{t("common.back")}</Button>
          {glossaryDetailExists ? (
            <Button
              type="primary"
              onClick={() => openModal("edit", glossaryDetailTarget)}
            >
              {t("admin.memoryEditItem")}
            </Button>
          ) : null}
        </Space>
      </div>
      <div className="memory-glossary-detail-page">
        <div className="memory-glossary-detail-card">
          <div className="memory-glossary-detail-title">
            <h3>{glossaryDetailTarget.term}</h3>
            <Tag color={glossarySourceColorMap[glossaryDetailTarget.source]}>
              {glossarySourceLabelMap[glossaryDetailTarget.source]}
            </Tag>
          </div>
          <div className="memory-form-field memory-form-field-full">
            <label>{t("admin.memoryGlossaryAliases")}</label>
            <div className="memory-tag-group">
              {glossaryDetailTarget.aliases.length ? (
                glossaryDetailTarget.aliases.map((alias: string) => (
                  <Tag key={`detail-${alias}`}>{alias}</Tag>
                ))
              ) : (
                <span className="memory-content-preview">-</span>
              )}
            </div>
          </div>
          <div className="memory-form-field memory-form-field-full">
            <label>{t("admin.memoryContent")}</label>
            <div className="memory-glossary-detail-content">
              {glossaryDetailTarget.content}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
