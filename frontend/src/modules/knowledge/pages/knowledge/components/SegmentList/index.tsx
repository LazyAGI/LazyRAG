import { Empty } from "antd";
import { forwardRef, useImperativeHandle, useRef } from "react";
import { Segment } from "@/api/generated/knowledge-client";
import { Virtuoso } from "react-virtuoso";

import SegmentCard from "../SegmentCard";
import SegmentDetailModal, {
  ISegmentDetailModalRef,
} from "../SegmentDetailModal";
import Rendering from "@/modules/knowledge/components/Rendering";
import "./index.scss";

export interface SegmentListImperativeProps {
  openDetail: (data: Segment, group: string) => void;
}

interface IProps {
  segments: Segment[];
  group: string;
  editable: boolean;
  hasMoreSegment: boolean;
  onDelete?: (segment: Segment) => void;
  onRefresh: () => void;
  onUpdateStatus?: (
    segmentId: string,
    isActive: boolean,
    apiPromise: Promise<void>,
  ) => void;
  fetchSegments: (isMore: boolean) => void;
  contentReadOnly: boolean;
  onGetItemInfo?: (segment: Segment) => void;
  loading?: boolean;
  scrollToId?: string;
}

const SegmentList = forwardRef<SegmentListImperativeProps, IProps>(
  (props, ref) => {
    const {
      segments,
      group,
      editable,
      onDelete,
      onRefresh,
      onUpdateStatus,
      fetchSegments,
      hasMoreSegment,
      contentReadOnly = false,
      onGetItemInfo,
      loading = false,
      scrollToId,
    } = props;

    const segmentDetailRef = useRef<ISegmentDetailModalRef>(null);

    useImperativeHandle(ref, () => ({
      openDetail,
    }));

    function openDetail(data: Segment, name: string) {
      // 优先使用 onGetItemInfo 回调来定位原文位置
      if (onGetItemInfo) {
        onGetItemInfo(data);
      } else if (contentReadOnly) {
        // 如果没有 onGetItemInfo 回调，且为只读模式，则打开详情弹窗
        segmentDetailRef.current?.handleOpen(data, name);
      }
    }

    if (loading) {
      return <Rendering text={"加载中..."} />;
    }

    if (!segments || segments.length < 1) {
      return <Empty description={"暂无内容"} style={{ marginTop: 80 }} />;
    }

    return (
      <div
        className="segmentList"
        id={`scrollableDiv-${group}`}
        style={{ height: editable ? "calc(100% - 40px)" : "100%" }}
      >
        <Virtuoso
          style={{ height: "100%", width: "100%" }}
          totalCount={segments.length}
          className="segmentList-virtuoso scroll-container"
          initialTopMostItemIndex={
            scrollToId
              ? Math.max(
                  0,
                  segments.findIndex((item) => item.segment_id === scrollToId),
                )
              : 0
          }
          endReached={() => {
            if (hasMoreSegment) {
              fetchSegments(true);
            }
          }}
          data={segments}
          defaultItemHeight={50}
          itemContent={(index) => {
            const segment = segments[index];
            return (
              <SegmentCard
                key={segment.segment_id}
                segment={segment}
                group={group}
                onDelete={() => onDelete?.(segment)}
                onOpenDetail={() => openDetail(segment, group)}
                onRefresh={onRefresh}
                onUpdateStatus={onUpdateStatus}
                editable={editable}
                contentReadOnly={contentReadOnly}
              />
            );
          }}
        />
        <SegmentDetailModal
          ref={segmentDetailRef}
          onClose={onRefresh}
          editable={editable}
        />
      </div>
    );
  },
);

SegmentList.displayName = "SegmentList";

export default SegmentList;
