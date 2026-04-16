import { Button, Input, Popover } from "antd";
import {
  SearchOutlined,
  CheckOutlined,
  PushpinOutlined,
  PushpinFilled,
} from "@ant-design/icons";
import {
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
} from "react";
import {
  KnowledgeBaseServiceApi,
} from "@/modules/chat/utils/request";
import { Dataset } from "@/api/generated/knowledge-client";
import KnowledgeIcon from "../../assets/icons/knowledge.svg?react";
import "./index.scss";
import { debounce } from "lodash";
import { ChatConfig } from "../ChatConfigs";
import { useTranslation } from "react-i18next";

export interface ChatSelectorProps {
  chatConfig: ChatConfig;
  onChange?: (
    knowledgeIds: string[],
    creators: string[],
    tags: string[],
  ) => void;
}

export interface ChatSelectorImperativeProps {
  open: (triggerElement: HTMLElement) => void;
  close: () => void;
}

const ChatSelector = forwardRef<ChatSelectorImperativeProps, ChatSelectorProps>(
  (props, ref) => {
    const { chatConfig, onChange } = props;
    const { t } = useTranslation();

    const [knowledgeBaseList, setKnowledgeBaseList] = useState<Dataset[]>([]);
    const [filteredList, setFilteredList] = useState<Dataset[]>([]);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [open, setOpen] = useState(false);
    const [knowledgeLoading, setKnowledgeLoading] = useState(false);
    const [defaultKnowledgeId, setDefaultKnowledgeId] = useState<string[]>([]);
    const [searchValue, setSearchValue] = useState<string>("");
    const isResettingSelectionRef = useRef(false);
    const isUpdatingDefaultRef = useRef(false);
    const selectedIdsRef = useRef<string[]>([]);

    useEffect(() => {
      selectedIdsRef.current = selectedIds;
    }, [selectedIds]);

    function getDefaultDatasetIds(datasets: Dataset[]) {
      return (datasets
        ?.filter((it) => it?.default_dataset)
        ?.map((k) => k.dataset_id)
        .filter(Boolean) as string[]) || [];
    }

    function mergeSelectedIds(...groups: Array<Array<string | undefined>>) {
      return [
        ...new Set(groups.flat().filter((id): id is string => Boolean(id))),
      ];
    }

    useEffect(() => {
      if (
        isResettingSelectionRef.current ||
        isUpdatingDefaultRef.current
      ) {
        return;
      }
      const setData = new Set([
        ...defaultKnowledgeId,
        ...(chatConfig?.knowledgeBaseId || []),
      ]);
      setSelectedIds([...setData]);
    }, [chatConfig, defaultKnowledgeId]);

    useEffect(() => {
      const hasDocumentFilters =
        (chatConfig?.creators?.length ?? 0) > 0 ||
        (chatConfig?.tags?.length ?? 0) > 0;

      if (!hasDocumentFilters) {
        return;
      }

      onChange?.(
        mergeSelectedIds(defaultKnowledgeId, chatConfig?.knowledgeBaseId ?? []),
        [],
        [],
      );
    }, [chatConfig, defaultKnowledgeId, onChange]);

    useImperativeHandle(ref, () => ({
      open: () => {
        setOpen(true);
      },
      close: () => setOpen(false),
    }));

    useEffect(() => {
      getKnowledgeBaseList();
    }, []);

    function getKnowledgeBaseList() {
      setKnowledgeLoading(true);
      KnowledgeBaseServiceApi()
        .datasetServiceListDatasets({ pageSize: 1000 })
        .then((res) => {
          const datasets = res.data.datasets || [];
          setKnowledgeBaseList(datasets);
          setFilteredList(datasets);
          const defaultIds = getDefaultDatasetIds(datasets);
          setDefaultKnowledgeId(defaultIds);
          const mergedIds = mergeSelectedIds(
            defaultIds,
            chatConfig?.knowledgeBaseId ?? [],
          );
          setSelectedIds(mergedIds);
          if (
            defaultIds.length > 0 &&
            (!chatConfig?.knowledgeBaseId ||
              chatConfig.knowledgeBaseId.length === 0)
          ) {
            onChange?.(
              mergedIds,
              [],
              [],
            );
          }
        })
        .finally(() => setKnowledgeLoading(false));
    }

    function refreshKnowledgeBaseListPreservingSelection() {
      isUpdatingDefaultRef.current = true;
      setKnowledgeLoading(true);
      KnowledgeBaseServiceApi()
        .datasetServiceListDatasets({ pageSize: 1000 })
        .then((res) => {
          const datasets = res.data.datasets || [];
          setKnowledgeBaseList(datasets);
          setFilteredList(datasets);
          const defaultIds = getDefaultDatasetIds(datasets);
          setDefaultKnowledgeId(defaultIds);

          const mergedIds = mergeSelectedIds(
            defaultIds,
            selectedIdsRef.current,
          );
          setSelectedIds(mergedIds);
          onChange?.(
            mergedIds,
            [],
            [],
          );
        })
        .finally(() => {
          setKnowledgeLoading(false);
          window.setTimeout(() => {
            isUpdatingDefaultRef.current = false;
          }, 0);
        });
    }

    const filterKnowledgeBaseListFn = debounce((search: string) => {
      setSearchValue(search);
    }, 300);

    const sortedAndFilteredList = useMemo(() => {
      let list = [...knowledgeBaseList];
      const originalIndexMap = new Map(
        knowledgeBaseList.map((item, index) => [item.dataset_id || `idx-${index}`, index]),
      );

      if (searchValue.trim()) {
        list = list.filter((item) =>
          item.display_name?.toLowerCase().includes(searchValue.toLowerCase()),
        );
      }

      list.sort((a, b) => {
        const aDefault = !!a.default_dataset;
        const bDefault = !!b.default_dataset;
        const aSelected = selectedIds.includes(a.dataset_id || "");
        const bSelected = selectedIds.includes(b.dataset_id || "");
        const aIndex = originalIndexMap.get(a.dataset_id || "") ?? 0;
        const bIndex = originalIndexMap.get(b.dataset_id || "") ?? 0;

        if (aDefault && !bDefault) {
          return -1;
        }
        if (!aDefault && bDefault) {
          return 1;
        }

        if (aSelected && !bSelected) {
          return -1;
        }
        if (!aSelected && bSelected) {
          return 1;
        }

        return aIndex - bIndex;
      });

      return list;
    }, [knowledgeBaseList, selectedIds, searchValue]);

    useEffect(() => {
      setFilteredList(sortedAndFilteredList);
    }, [sortedAndFilteredList]);

    function handleItemClick(item: Dataset) {
      const datasetId = item.dataset_id;
      if (!datasetId) {
        return;
      }

      // Default knowledge bases should stay selected until the pin is removed.
      if (item.default_dataset) {
        const mergedIds = mergeSelectedIds(
          defaultKnowledgeId,
          selectedIdsRef.current,
        );
        if (mergedIds.length !== selectedIdsRef.current.length) {
          setSelectedIds(mergedIds);
          onChange?.(
            mergedIds,
            [],
            [],
          );
        }
        return;
      }

      const newSelectedIds = selectedIds.includes(datasetId)
        ? selectedIds.filter((id) => id !== datasetId)
        : [...selectedIds, datasetId];

      setSelectedIds(newSelectedIds);
      onChange?.(
        newSelectedIds,
        [],
        [],
      );
    }

    function unSetDefaultDatasetFn(item: Dataset) {
      KnowledgeBaseServiceApi()
        .datasetServiceUnsetDefaultDataset({
          dataset: item?.dataset_id ?? "",
          unsetDefaultDatasetRequest: { name: item?.name ?? "" },
        })
        .then(() => {
          refreshKnowledgeBaseListPreservingSelection();
        });
    }

    function setDefaultDatasetFn(item: Dataset) {
      KnowledgeBaseServiceApi()
        .datasetServiceSetDefaultDataset({
          dataset: item?.dataset_id ?? "",
          setDefaultDatasetRequest: { name: item?.name ?? "" },
        })
        .then(() => {
          refreshKnowledgeBaseListPreservingSelection();
        });
    }

    function renderDefaultItem(
      item: Dataset,
      isSelected: boolean,
      isDefault: boolean,
    ) {
      if (isSelected) {
        if (isDefault) {
          return (
            <PushpinFilled
              className="defaultDataset"
              onClick={(e) => {
                e.stopPropagation();
                unSetDefaultDatasetFn(item);
              }}
            />
          );
        }
        return (
          <PushpinOutlined
            className="cancelDefaultDataset"
            onClick={(e) => {
              e.stopPropagation();
              setDefaultDatasetFn(item);
            }}
          />
        );
      }
      return null;
    }

    function renderContent() {
      return (
        <div className="chat-selector-container">
          <div className="chat-selector-search-box">
            <Input
              suffix={<SearchOutlined style={{ color: "#999" }} />}
              placeholder={t("chat.searchKnowledge")}
              onChange={(e) => filterKnowledgeBaseListFn(e.target.value)}
              className="chat-selector-search-input"
              autoFocus
              disabled={knowledgeLoading}
            />
            <Button
              type="link"
              disabled={knowledgeLoading}
              onClick={() => {
                // setSearchValue('');
                isResettingSelectionRef.current = true;
                setKnowledgeLoading(true);
                KnowledgeBaseServiceApi()
                  .datasetServiceResetDefaultDatasets({ body: {} })
                  .then(() =>
                    KnowledgeBaseServiceApi().datasetServiceListDatasets({
                      pageSize: 1000,
                    }),
                  )
                  .then((res) => {
                    const datasets = res.data.datasets || [];
                    setKnowledgeBaseList(datasets);
                    const defaultIds =
                      (datasets
                        ?.filter((it) => it?.default_dataset)
                        ?.map((k) => k.dataset_id)
                        .filter(Boolean) as string[]) || [];
                    setDefaultKnowledgeId(defaultIds);
                    setSelectedIds(defaultIds);
                    onChange?.(
                      defaultIds,
                      [],
                      [],
                    );
                  })
                  .finally(() => {
                    isResettingSelectionRef.current = false;
                    setKnowledgeLoading(false);
                  });
              }}
              style={{ padding: 0, marginLeft: 16 }}
            >
              {t("chat.reset")}
            </Button>
            {selectedIds.length !== knowledgeBaseList.length ? (
              <Button
                type="link"
                disabled={knowledgeLoading}
                onClick={() => {
                  const allIds = knowledgeBaseList.map(
                    (item) => item.dataset_id || "",
                  );
                  setSelectedIds(allIds);
                  onChange?.(
                    allIds,
                    [],
                    [],
                  );
                }}
                style={{ padding: 0, marginLeft: 16 }}
              >
                {t("chat.selectAll")}
              </Button>
            ) : (
              <Button
                type="link"
                style={{ padding: 0, marginLeft: 16 }}
                onClick={() => {
                  setSelectedIds(defaultKnowledgeId);
                  onChange?.(
                    defaultKnowledgeId,
                    [],
                    [],
                  );
                }}
              >
                {t("chat.cancelSelectAll")}
              </Button>
            )}
          </div>
          <div className="chat-selector-list-container">
            {filteredList.map((item) => {
              const isSelected = selectedIds.includes(item.dataset_id || "");
              const isDefault = !!item?.default_dataset;
              return (
                <div
                  key={item.dataset_id}
                  className={`chat-selector-list-item ${isDefault || isSelected ? "selected" : ""}`}
                  onClick={() => handleItemClick(item)}
                >
                  <span className="chat-selector-item-label">
                    {item.display_name}
                  </span>
                  {renderDefaultItem(item, isSelected, isDefault)}
                  {(isDefault || isSelected) && (
                    <CheckOutlined className="chat-selector-check-icon" />
                  )}
                </div>
              );
            })}
            {knowledgeLoading ? (
              <div className="chat-selector-empty-text">{t("chat.loadingWait")}</div>
            ) : !filteredList?.length ? (
              <div className="chat-selector-empty-text">{t("chat.noData")}</div>
            ) : null}
          </div>
        </div>
      );
    }

    return (
      <div className="chat-selector-wrapper">
        <Popover
          content={renderContent()}
          classNames={{ root: "knowledgePopover" }}
          trigger="click"
          open={open}
          onOpenChange={(bool) => setOpen(bool)}
        >
          <div
            className={`input-bottom-actions-left-item ${open || selectedIds.length > 0 ? "selected" : ""}`}
          >
            <KnowledgeIcon />
            {t("chat.knowledgeBase")}
          </div>
        </Popover>
      </div>
    );
  },
);

export default ChatSelector;
