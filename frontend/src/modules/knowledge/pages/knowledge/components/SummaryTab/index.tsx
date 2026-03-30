import { useEffect, useRef, useState } from "react";
import { Doc, Segment } from "@/api/generated/knowledge-client";
import { SegmentServiceApi } from "@/modules/knowledge/utils/request";
import SegmentList, { SegmentListImperativeProps } from "../SegmentList";
import { CARD_PAGE_SIZE } from "@/modules/knowledge/constants/common";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

const SummaryTab = (props: { detail: Doc; type: string }) => {
  const { detail, type } = props;
  const [segments, setSegments] = useState<Segment[]>([]);
  const segmentListRef = useRef<SegmentListImperativeProps>(null);
  const [pageToken, setPageToken] = useState("");

  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );
  function fetchSegments(isMore = false) {
    SegmentServiceApi()
      .segmentServiceSearchSegments({
        dataset: detail.dataset_id || "",
        document: detail.document_id || "",
        searchSegmentsRequest: {
          parent: "",
          group: type,
          page_size: isMore ? CARD_PAGE_SIZE : 10,
          page_token: isMore ? pageToken : "",
        },
      })
      .then((res) => {
        setSegments(res.data.segments || []);
        setPageToken(res.data.next_page_token || "");
      });
  }

  useEffect(() => {
    if (detail.dataset_id && detail.document_id) {
      fetchSegments();
    }
  }, [detail]);

  return (
    <SegmentList
      ref={segmentListRef}
      segments={segments}
      group={type}
      onRefresh={() => {
        fetchSegments();
      }}
      editable={false}
      hasMoreSegment={false}
      fetchSegments={(isMore) => {
        fetchSegments(isMore);
      }}
      contentReadOnly={!hasWritePermission}
    />
  );
};

export default SummaryTab;
