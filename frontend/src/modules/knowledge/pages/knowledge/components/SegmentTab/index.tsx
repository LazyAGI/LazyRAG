import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useImmer } from "use-immer";
import SegmentList, { SegmentListImperativeProps } from "../SegmentList";
import { Segment } from "@/api/generated/knowledge-client";
import { from, expand, EMPTY, scan, takeWhile, map } from "rxjs";
import { message, Modal, Select } from "antd";
import { SegmentServiceApi } from "@/modules/knowledge/utils/request";
import { CARD_PAGE_SIZE } from "@/modules/knowledge/constants/common";
import { useDatasetPermissionStore } from "@/modules/knowledge/store/dataset_permission";

const MAX_SIZE = 100;

interface DocumentDetail {
  dataset_id?: string;
  document_id?: string;
}

interface SegmentTabProps {
  detail: DocumentDetail;
  names?: string[];
  editable?: boolean;
  type?: string;
  onGetItemInfo?: (info: Segment) => void;
}

const SegmentTab = (props: SegmentTabProps) => {
  const { detail, names = [], editable = false, type, onGetItemInfo } = props;

  const [splitTypes, setSplitTypes] = useState<string[]>([]);
  const [currentType, setCurrentType] = useState(type || names[0] || "");
  const [segments, setSegments] = useImmer<Segment[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextPageToken, setNextPageToken] = useState("");
  const [searchParams] = useSearchParams();
  const segmentListRef = useRef<SegmentListImperativeProps>(null);
  const [loading, setLoading] = useState(false);

  // 使用权限 store
  const hasWritePermission = useDatasetPermissionStore((state) =>
    state.hasWritePermission(),
  );

  // 根据权限控制是否可编辑
  const canEdit = editable && hasWritePermission;

  const segmentNumber = useMemo(() => {
    return searchParams.get("number")
      ? Number(searchParams.get("number")) + 2
      : CARD_PAGE_SIZE;
  }, [searchParams]);

  const segmentId = useMemo(() => {
    return searchParams.get("segement_id") || "";
  }, [searchParams]);

  // 统一的数据获取函数
  const fetchSegmentsData = useCallback(
    async (tp: string, limit: number, token = "", isLoading = true) => {
      try {
        if (isLoading) {
          setLoading(true);
        }
        const res = await SegmentServiceApi()
          .segmentServiceSearchSegments({
            dataset: detail.dataset_id || "",
            document: detail.document_id || "",
            searchSegmentsRequest: {
              parent: "",
              group: tp,
              page_size: limit,
              page_token: token,
            },
          })
          .finally(() => {
            setLoading(false);
          });
        return {
          segments: res.data.segments || [],
          nextPageToken: res.data.next_page_token || "",
        };
      } catch (error) {
        setLoading(false);
        console.error("Error fetching segments:", error);
        throw error;
      }
    },
    [detail],
  );

  // 统一的数据加载函数
  const loadSegmentsData = useCallback(
    (targetNumber: number, targetType: string) => {
      // 如果需要的数据量大于一页，使用 RxJS 流批量加载
      if (targetNumber > CARD_PAGE_SIZE) {
        // 初次请求取 min(MAX_SIZE, targetNumber)
        const initialLimit = Math.min(targetNumber, MAX_SIZE);
        let lastResponse: {
          segments: Segment[];
          nextPageToken: string;
        } | null = null;
        // 用于按剩余数量调整每次请求大小，避免过取
        let accumulatedCount = 0;

        from(fetchSegmentsData(targetType, initialLimit))
          .pipe(
            expand((res) => {
              const result = res as {
                segments: Segment[];
                nextPageToken: string;
              };
              lastResponse = result; // 保存最后一次响应
              accumulatedCount += result.segments.length;

              const remaining = targetNumber - accumulatedCount;
              // 没有更多页、或已满足目标、或异常返回 0 条时停止
              if (
                !result.nextPageToken ||
                remaining <= 0 ||
                result.segments.length === 0
              ) {
                return EMPTY;
              }

              const nextLimit = Math.min(MAX_SIZE, remaining);
              return from(
                fetchSegmentsData(targetType, nextLimit, result.nextPageToken),
              );
            }),
            scan((acc, res) => {
              const result = res as {
                segments: Segment[];
                nextPageToken: string;
              };
              lastResponse = result; // 更新最后一次响应
              return [...acc, ...result.segments];
            }, [] as Segment[]),
            // 达到目标时包含该次发射
            takeWhile((all) => (all as Segment[]).length < targetNumber, true),
            map((all) => {
              const result = (all as Segment[]).slice(0, targetNumber);
              return result;
            }),
          )
          .subscribe({
            next: (data) => {
              setSegments(data);
              // 根据最后一次请求的结果设置分页状态
              if (lastResponse) {
                setNextPageToken(lastResponse.nextPageToken);
                setHasMore(
                  !!lastResponse.nextPageToken && data.length === targetNumber,
                );
              }
            },
            error: (error) => {
              console.error("Error in batch data loading:", error);
            },
          });
      } else {
        // 对于小数据量，直接获取一页数据并设置分页状态
        from(fetchSegmentsData(targetType, CARD_PAGE_SIZE)).subscribe({
          next: (result) => {
            setSegments(result.segments);
            setNextPageToken(result.nextPageToken);
            setHasMore(!!result.nextPageToken);
          },
          error: (error) => {
            console.error("Error in page data loading:", error);
          },
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fetchSegmentsData],
  );

  // 加载更多数据的函数（使用 RxJS 流）
  const loadMoreSegments = useCallback(() => {
    if (!hasMore || !nextPageToken) {
      return;
    }

    from(
      fetchSegmentsData(currentType, CARD_PAGE_SIZE, nextPageToken, false),
    ).subscribe({
      next: (result) => {
        setSegments((prev) => [...prev, ...result.segments]);
        setNextPageToken(result.nextPageToken);
        setHasMore(!!result.nextPageToken);
      },
      error: (error) => {
        console.error("Error loading more segments:", error);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentType, nextPageToken, hasMore, fetchSegmentsData]);

  // 初始化数据
  useEffect(() => {
    if (!detail?.dataset_id || !detail?.document_id) {
      return;
    }

    if (editable && names) {
      setSplitTypes(names);
    }

    const newCurrentType = type || (names && names[0]) || "";
    setCurrentType(newCurrentType);

    // 重置状态
    setNextPageToken("");
    setHasMore(false);

    // 使用统一的数据加载函数，初始化时需要滚动定位
    loadSegmentsData(segmentNumber, newCurrentType);
  }, [
    detail?.dataset_id,
    detail?.document_id,
    names,
    editable,
    type,
    segmentNumber,
    loadSegmentsData,
  ]);

  // 快速对比函数：检查服务器数据是否与本地数据不同
  const isDifferentFromLocal = useCallback(
    (serverSegments: Segment[]) => {
      if (serverSegments.length !== segments.length) {
        return true;
      }

      return serverSegments.some((serverSeg, idx) => {
        const localSeg = segments[idx];
        return (
          serverSeg.segment_id !== localSeg?.segment_id ||
          serverSeg.is_active !== localSeg?.is_active ||
          serverSeg.content !== localSeg?.content
        );
      });
    },
    [segments],
  );

  // 删除分段的处理函数
  const onDeleteSegment = useCallback(
    (segment: Segment) => {
      Modal.confirm({
        title: "提示",
        content: `确定删除分段 ${segment.number}？`,
        centered: true,
        okType: "danger",
        onOk() {
          // 1. 立即用 immer 更新本地状态（保持滚动位置）
          setSegments((draft) => {
            const index = draft.findIndex(
              (s) => s.segment_id === segment.segment_id,
            );
            if (index > -1) {
              draft.splice(index, 1);
            }
          });

          // 2. 发起删除请求
          SegmentServiceApi()
            .segmentServiceDeleteSegment({
              dataset: segment.dataset_id || "",
              group: currentType,
              document: segment.document_id || "",
              segment: segment.segment_id || "",
            })
            .then(() => {
              message.success("删除分段成功");

              // 3. 后台获取最新数据并对比
              fetchSegmentsData(currentType, segments.length - 1).then(
                (result) => {
                  // 4. 快速对比：只在数据不同时才更新（检测协同编辑）
                  if (isDifferentFromLocal(result.segments)) {
                    setSegments(result.segments);
                    setNextPageToken(result.nextPageToken);
                    setHasMore(!!result.nextPageToken);
                  }
                },
              );
            });
        },
      });
    },
    [
      currentType,
      segments,
      setSegments,
      fetchSegmentsData,
      isDifferentFromLocal,
    ],
  );

  // 切换分段类型的处理函数
  const onSplitTypeChanged = useCallback(
    (newType: string) => {
      setCurrentType(newType);
      setNextPageToken("");
      setHasMore(false);
      // 切换类型后重新加载当前数量的数据
      loadSegmentsData(segments.length || CARD_PAGE_SIZE, newType);
    },
    [segments.length, loadSegmentsData],
  );

  // 更新分段状态的处理函数
  const onUpdateSegmentStatus = useCallback(
    (targetSegmentId: string, isActive: boolean, apiPromise: Promise<void>) => {
      // 1. 立即用 immer 更新本地状态（保持滚动位置）
      setSegments((draft) => {
        const segment = draft.find((s) => s.segment_id === targetSegmentId);
        if (segment) {
          segment.is_active = isActive;
        }
      });

      // 2. 等待 API 成功后再获取数据（确保服务器已有用户修改）
      apiPromise
        .then(() => {
          // 3. API 成功，获取最新数据（此时应包含用户的修改）
          return fetchSegmentsData(currentType, segments.length, "", false);
        })
        .then((result) => {
          // 4. 智能对比：只在数据不同时才更新（检测协同编辑）
          if (isDifferentFromLocal(result.segments)) {
            setSegments(result.segments);
            setNextPageToken(result.nextPageToken);
            setHasMore(!!result.nextPageToken);
          }
        })
        .catch((error) => {
          console.error("更新状态失败:", error);
          // 5. API 失败，回滚本地状态
          setSegments((draft) => {
            const segment = draft.find((s) => s.segment_id === targetSegmentId);
            if (segment) {
              segment.is_active = !isActive; // 恢复原状态
            }
          });
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentType, segments.length, fetchSegmentsData, isDifferentFromLocal],
  );

  // 获取更多分段的处理函数
  const handleFetchMore = useCallback(
    (isMore: boolean) => {
      if (isMore && hasMore) {
        loadMoreSegments();
      } else {
        // 刷新当前数据
        loadSegmentsData(segments.length || CARD_PAGE_SIZE, currentType);
      }
    },
    [hasMore, loadMoreSegments, segments.length, currentType, loadSegmentsData],
  );

  return (
    <div className="flex-1 flex-col overflow-hidden">
      {splitTypes.length > 1 ? (
        <Select
          value={currentType}
          options={splitTypes.map((splitType) => ({
            value: splitType,
            label: splitType,
          }))}
          onChange={onSplitTypeChanged}
          style={{ marginBottom: 8, width: 120 }}
        />
      ) : null}

      <SegmentList
        ref={segmentListRef}
        segments={segments}
        group={currentType}
        onDelete={onDeleteSegment}
        onRefresh={() => handleFetchMore(false)}
        onUpdateStatus={onUpdateSegmentStatus}
        editable={canEdit}
        fetchSegments={handleFetchMore}
        hasMoreSegment={hasMore}
        contentReadOnly={!canEdit}
        onGetItemInfo={onGetItemInfo}
        loading={loading}
        scrollToId={segmentId}
      />
    </div>
  );
};

export default SegmentTab;
