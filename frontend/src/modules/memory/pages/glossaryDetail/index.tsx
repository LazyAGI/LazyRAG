import { Button, Space, Tag } from "antd";
import { DetailPageHeader } from "@/components/ui";
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
      <DetailPageHeader
        className="memory-glossary-detail-page-header"
        title={t("admin.memoryGlossaryDetailTitle")}
        description={glossaryDetailTarget.term}
        onBack={closeGlossaryDetail}
      />
      <div className="memory-glossary-detail-page">
        <div className="memory-glossary-detail-card">
          <div className="memory-glossary-detail-title">
            <div className="memory-glossary-detail-title-copy">
              <h3>{glossaryDetailTarget.term}</h3>
            </div>
            <div className="memory-skill-detail-meta">
              <Tag color={glossarySourceColorMap[glossaryDetailTarget.source]}>
                {glossarySourceLabelMap[glossaryDetailTarget.source]}
              </Tag>
            </div>
          </div>
          <div className="memory-glossary-detail-aliases">
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
          <div className="memory-glossary-detail-body">
            <div className="memory-skill-detail-editor-toolbar">
              <div className="memory-skill-detail-editor-heading">
                <label>{t("admin.memoryContent")}</label>
              </div>
              {glossaryDetailExists ? (
                <Space size={8}>
                  <Button
                    type="primary"
                    onClick={() => openModal("edit", glossaryDetailTarget)}
                  >
                    {t("admin.memoryEditItem")}
                  </Button>
                </Space>
              ) : null}
            </div>
            <div className="memory-glossary-detail-content">
              {glossaryDetailTarget.content}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
