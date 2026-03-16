import { message, Tag, Row, Col } from "antd";
import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { CopyOutlined } from "@ant-design/icons";
import moment from "moment";
import { Doc, Segment } from "@/api/generated/knowledge-client";

import { TIME_FORMAT } from "@/modules/knowledge/constants/common";
import FileUtils from "@/modules/knowledge/utils/file";
import FileViewer from "@/modules/knowledge/components/FileViewer";
import KnowledgeTabs from "./components/KnowledgeTabs";
import {
  DocumentServiceApi,
  SegmentServiceApi,
  KnowledgeBaseServiceApi,
} from "@/modules/knowledge/utils/request";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";
import { DetailPageHeader } from "@/components/ui";
import "./index.scss";

const Detail = () => {
  const [knowledgeDetail, setKnowledgeDetail] = useState<Doc>();

  const { knowledgeBaseId = "", knowledgeId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [segmentDetail, setSegmentDetail] = useState<Segment>();

  // 使用权限 store
  const {
    getDatasetDetail: getKbDetail,
    setCurrentDataset,
    clearDataset,
  } = useDatasetPermissionStore();
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );

  const group = useMemo(() => {
    return searchParams.get("group_name") || "";
  }, [searchParams]);

  const segmentId = useMemo(() => {
    return searchParams.get("segement_id") || "";
  }, [searchParams]);

  const getDetail = useCallback(() => {
    DocumentServiceApi()
      .documentServiceGetDocument({
        dataset: knowledgeBaseId,
        document: knowledgeId,
      })
      .then((res) => {
        setKnowledgeDetail(res.data);
      });
  }, [knowledgeBaseId, knowledgeId]);

  // 获取知识库权限信息
  const getDatasetDetail = useCallback(() => {
    KnowledgeBaseServiceApi()
      .datasetServiceGetDataset({ dataset: knowledgeBaseId })
      .then((res) => {
        // 更新权限 store
        setCurrentDataset(res.data);
      });
  }, [knowledgeBaseId, setCurrentDataset]);

  useEffect(() => {
    getDetail();
    getDatasetDetail();

    return () => {
      // 组件卸载时清除权限信息
      clearDataset();
    };
  }, [getDetail, getDatasetDetail, clearDataset]);

  const getSegmentDetail = useCallback(() => {
    if (group && segmentId) {
      SegmentServiceApi()
        .segmentServiceGetSegment({
          dataset: knowledgeBaseId,
          document: knowledgeId,
          segment: segmentId,
          group: group,
        })
        .then((res) => {
          setSegmentDetail(res.data);
        });
    }
  }, [group, segmentId, knowledgeBaseId, knowledgeId]);

  useEffect(() => {
    getSegmentDetail();
  }, [group, segmentId, getSegmentDetail]);

  return (
    <div className="knowledge-container !h-full !items-start">
      <DetailPageHeader
        breadcrumbs={[
          { title: "知识库", href: "/appplatform/lib/knowledge/list" },
          {
            title: getKbDetail()?.display_name || "知识库详情",
            href: `/appplatform/lib/knowledge/detail/${getKbDetail()?.dataset_id}`,
          },
          { title: knowledgeDetail?.display_name },
        ]}
        title={knowledgeDetail?.display_name}
        onBack={() => {
          const bool = ["aiwrite", "aireview", "chat"].includes(
            searchParams.get("from") ?? "",
          );
          if (bool) {
            navigate(`/detail/${knowledgeBaseId}?from=aiwrite`);
          } else {
            navigate(-1);
          }
        }}
        titleExtra={
          <div>
            <span
              style={{
                marginRight: "4px",
                color: "var(--color-text-description)",
              }}
            >
              ID: {knowledgeId}
            </span>
            <CopyOutlined
              style={{ color: "var(--color-text-description)" }}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(knowledgeId);
                  message.success("复制成功");
                } catch {
                  message.success("复制失败，请手动复制");
                }
              }}
            />
          </div>
        }
        extraContent={[
          { label: "来源", value: "本地文件" },
          {
            label: "创建时间",
            value: moment(knowledgeDetail?.create_time).format(TIME_FORMAT),
          },
          {
            label: "创建人",
            value: knowledgeDetail?.creator || "-",
          },
          {
            label: "原始文件",
            value: (
              <a
                href={knowledgeDetail?.uri}
                rel="noreferrer noopener"
                target="_blank"
                title={knowledgeDetail?.display_name}
              >
                {knowledgeDetail?.display_name}
              </a>
            ),
            hidden: !hasWritePermission,
          },
          {
            label: "更新时间",
            value: moment(knowledgeDetail?.update_time).format(TIME_FORMAT),
          },
          {
            label: "大小",
            value:
              FileUtils.formatFileSize(knowledgeDetail?.document_size) || "-",
          },
          {
            label: "标签",
            value:
              knowledgeDetail?.tags && knowledgeDetail?.tags.length > 0
                ? knowledgeDetail.tags.map((tag) => (
                    <Tag style={{ marginLeft: "8px" }} key={tag}>
                      {tag}
                    </Tag>
                  ))
                : "-",
          },
        ]}
      />
      <Row gutter={[12, 12]} className="mt-6 w-full flex-1">
        <Col span={15}>
          <div className="h-full overflow-hidden">
            <FileViewer
              file={knowledgeDetail?.convert_file_uri || knowledgeDetail?.uri}
              fileName={knowledgeDetail?.display_name || ""}
              segment={segmentDetail}
            />
          </div>
        </Col>
        <Col span={9}>
          <div className="h-full overflow-hidden pb-1">
            {knowledgeDetail && (
              <KnowledgeTabs
                knowledgeDetail={knowledgeDetail}
                onGetItemInfo={(data) => {
                  setSegmentDetail(data);
                }}
              />
            )}
          </div>
        </Col>
      </Row>
    </div>
  );
};

export default Detail;
