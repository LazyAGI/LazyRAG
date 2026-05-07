import { Button, Empty, Space, Tag } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { useMemo } from "react";
import { useParams } from "react-router-dom";
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
      <div className="memory-page-header">
        <div>
          <h2 className="admin-page-title">
            {t("admin.memoryExperienceDetailTitle")}
          </h2>
          <p className="memory-page-subtitle">
            {experience?.title || t("admin.memoryDiffTargetMissing")}
          </p>
        </div>
        <Space>
          <Button onClick={() => navigateToMemoryList("experience")}>
            {t("common.back")}
          </Button>
          {experience ? (
            <Button type="primary" onClick={() => openModal("edit", experience)}>
              {t("admin.memoryEditItem")}
            </Button>
          ) : null}
        </Space>
      </div>

      {!experience ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("admin.memoryDiffTargetMissing")}
        />
      ) : (
        <div className="memory-experience-detail-card">
          <div className="memory-experience-detail-title">
            <div>
              <h3>{experience.title}</h3>
            </div>
            <div className="memory-skill-detail-meta">
              {experience.protect ? (
                <Tag className="memory-protect-tag" bordered={false}>
                  <LockOutlined />
                  <span>{t("admin.memoryProtect")}</span>
                </Tag>
              ) : null}
            </div>
          </div>

          <div className="memory-form-field memory-form-field-full">
            <label>{t("admin.memoryExperienceDetailContent")}</label>
            <div className="memory-experience-detail-content">
              <pre>{experience.content || "-"}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
