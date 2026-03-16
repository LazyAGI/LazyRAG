import { useEffect, useState } from "react";
import { Doc, Segment } from "@/api/generated/knowledge-client";
import { SegmentServiceApi } from "@/modules/knowledge/utils/request";
import { Button, Modal, Tooltip } from "antd";
import type { TablePaginationConfig } from "antd";
import UIUtils from "@/modules/knowledge/utils/ui";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

import { ListPageTable } from "@/components/ui";

const paginationInit = {
  current: 1,
  pageSize: 10,
  total: 0,
};

const QaTab = (props: { detail: Doc; type: string }) => {
  const { detail, type } = props;
  const [segments, setSegments] = useState<Segment[]>([]);
  const [pagination, setPagination] =
    useState<TablePaginationConfig>(paginationInit);
  const [loading, setLoading] = useState(false);

  // 使用权限 store
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );

  function fetchSegments(page = 1, pageSize = 10) {
    setLoading(true);
    SegmentServiceApi()
      .segmentServiceSearchSegments({
        dataset: detail.dataset_id || "",
        document: detail.document_id || "",
        searchSegmentsRequest: {
          parent: "",
          group: type,
          page_size: pageSize,
          page_token: UIUtils.generatePageToken({
            page: page - 1,
            pageSize,
            total: pagination.total || 0,
          }),
        },
      })
      .then((res) => {
        setSegments(
          res.data.segments?.map((item) => ({
            segment_id: item.segment_id,
            content: item.content,
            answer: item.answer,
          })) || [],
        );
        setPagination((pre) => ({
          ...pre,
          total: res?.data?.total_size || 0,
        }));
      })
      .finally(() => {
        setLoading(false);
      });
  }

  function onDelete(segment_id: string) {
    Modal.confirm({
      title: "删除",
      content: "确定删除该问答对吗？",
      onOk: () => {
        SegmentServiceApi()
          .segmentServiceDeleteSegment({
            dataset: detail.dataset_id || "",
            document: detail.document_id || "",
            segment: segment_id,
            group: type,
          })
          .then(() => {
            fetchSegments();
          });
      },
    });
  }

  useEffect(() => {
    if (detail.dataset_id && detail.document_id) {
      fetchSegments();
    }
  }, [detail.dataset_id, detail.document_id]);

  const columns = [
    {
      title: "问题",
      dataIndex: "content",
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => {
        return (
          <Tooltip title={text} placement="topLeft">
            <span>{text}</span>
          </Tooltip>
        );
      },
    },
    {
      title: "答案",
      dataIndex: "answer",
      ellipsis: {
        showTitle: false,
      },
      render: (text: string) => {
        return (
          <Tooltip title={text} placement="topLeft">
            <span>{text}</span>
          </Tooltip>
        );
      },
    },
    {
      title: "操作",
      key: "action",
      width: 60,
      render: (record: Segment) => {
        // 只有写权限才显示删除按钮
        if (!hasWritePermission) {
          return null;
        }
        return (
          <Button
            type="link"
            danger
            className="!w-auto !min-w-auto !p-0"
            onClick={() => {
              onDelete(record.segment_id || "");
            }}
          >
            删除
          </Button>
        );
      },
    },
  ];

  return (
    <div className="h-[calc(100vh-300px)] w-full overflow-hidden">
      <div className="h-full w-full overflow-auto">
        <ListPageTable
          className="w-full"
          loading={loading}
          columns={columns}
          dataSource={segments}
          rowKey={(record) => record.segment_id || ""}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            showSizeChanger: true,
            total: pagination.total,
            showTotal: (total) => `共 ${total} 条`,
            pageSizeOptions: [10, 20, 50, 100],
            onChange: (page, pageSize) => {
              if (
                page !== pagination.current ||
                pageSize !== pagination.pageSize
              ) {
                setPagination((pre) => ({
                  ...pre,
                  current: page,
                  pageSize: pageSize,
                }));
                fetchSegments(page, pageSize);
              }
            },
          }}
        />
      </div>
    </div>
  );
};

export default QaTab;
