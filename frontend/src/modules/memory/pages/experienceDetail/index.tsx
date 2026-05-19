import { Button, Empty, Space, Tag } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { DetailPageHeader } from "@/components/ui";
import RouteLoading from "../../components/RouteLoading";
import { useMemoryManagementOutletContext } from "../../context";
import type { ExperienceAsset } from "../../shared";

export default function MemoryExperienceDetailPage() {
  const { itemId = "" } = useParams();
  const {
    t,
    experienceAssets,
    experienceInitialized,
    navigateToMemoryList,
    openModal,
  } = useMemoryManagementOutletContext();

  const experience = useMemo(
    () => experienceAssets.find((item: ExperienceAsset) => item.id === itemId) || null,
    [experienceAssets, itemId],
  );

  if (!experienceInitialized && !experience) {
    return <RouteLoading title={t("admin.memoryExperienceDetailTitle")} />;
  }

  return (
    <div className="memory-experience-detail-layout">
      <DetailPageHeader
        className="memory-experience-detail-page-header"
        title={t("admin.memoryExperienceDetailTitle")}
        description={experience?.title || t("admin.memoryDiffTargetMissing")}
        onBack={() => navigateToMemoryList("experience")}
      />

      {!experience ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("admin.memoryDiffTargetMissing")}
        />
      ) : (
        <div className="memory-experience-detail-card">
          <div className="memory-experience-detail-title">
            <div className="memory-experience-detail-title-copy">
              <h3>{experience.title}</h3>
            </div>
            <div className="memory-skill-detail-meta">
              {experience.protect ? (
                <Tag className="memory-protect-tag" bordered={false}>
                  <LockOutlined />
                  <span>{t("admin.memoryProtect", { defaultValue: "保护" })}</span>
                </Tag>
              ) : null}
            </div>
          </div>

          <div className="memory-experience-detail-body">
            <div className="memory-skill-detail-editor-toolbar">
              <div className="memory-skill-detail-editor-heading">
                <label>{t("admin.memoryExperienceDetailContent")}</label>
              </div>
              {experience ? (
                <Space size={8}>
                  <Button type="primary" onClick={() => openModal("edit", experience)}>
                    {t("admin.memoryEditItem")}
                  </Button>
                </Space>
              ) : null}
            </div>
            <div className="memory-experience-detail-content">
              <pre>{experience.content || "-"}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
