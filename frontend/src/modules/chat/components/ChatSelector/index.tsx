import { Button, Form, Input, Popover, Select, Space, Tag } from "antd";
import {
  SearchOutlined,
  CheckOutlined,
  PushpinOutlined,
  PushpinFilled,
  SettingOutlined,
  DownOutlined,
  UpOutlined,
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
  DocumentServiceApi,
  KnowledgeBaseServiceApi,
} from "@/modules/chat/utils/request";
import { Dataset, UserInfo } from "@/api/generated/knowledge-client";
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
    const [form] = Form.useForm();
    const { t } = useTranslation();

    const [knowledgeBaseList, setKnowledgeBaseList] = useState<Dataset[]>([]);
    const [filteredList, setFilteredList] = useState<Dataset[]>([]);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [open, setOpen] = useState(false);
    const [knowledgeLoading, setKnowledgeLoading] = useState(false);
    const [defaultKnowledgeId, setDefaultKnowledgeId] = useState<string[]>([]);
    const [creators, setCreators] = useState<UserInfo[]>([]);
    const [tags, setTags] = useState<string[]>([]);
    const [showConfig, setShowConfig] = useState<boolean>(false);
    const [searchValue, setSearchValue] = useState<string>("");
    const isResettingSelectionRef = useRef(false);

    useEffect(() => {
      if (isResettingSelectionRef.current) {
        return;
      }
      const setData = new Set([
        ...defaultKnowledgeId,
        ...(chatConfig?.knowledgeBaseId || []),
      ]);
      setSelectedIds([...setData]);
      form.setFieldsValue({
        creators: chatConfig?.creators || [],
        tags: chatConfig?.tags || [],
      });
    }, [chatConfig, defaultKnowledgeId]);

    useImperativeHandle(ref, () => ({
      open: () => {
        setOpen(true);
      },
      close: () => setOpen(false),
    }));

    useEffect(() => {
      getKnowledgeBaseList();
      fetchCreators();
      fetchTags();
    }, []);

    function fetchCreators() {
      DocumentServiceApi()
        .documentServiceAllDocumentCreators()
        .then((res) => {
          setCreators(res.data.creators || []);
        });
    }

    function fetchTags() {
      DocumentServiceApi()
        .documentServiceAllDocumentTags()
        .then((res) => {
          setTags(res.data.tags || []);
        });
    }

    function getKnowledgeBaseList() {
      setKnowledgeLoading(true);
      KnowledgeBaseServiceApi()
        .datasetServiceListDatasets({ pageSize: 1000 })
        .then((res) => {
          const datasets = res.data.datasets || [];
          setKnowledgeBaseList(datasets);
          setFilteredList(datasets);
          const defaultIds = datasets
            ?.filter((it) => it?.default_dataset)
            ?.map((k) => k.dataset_id) as string[];
          setDefaultKnowledgeId(defaultIds);
          const mergedIds = [
            ...new Set([...defaultIds, ...(chatConfig?.knowledgeBaseId ?? [])]),
          ];
          setSelectedIds(mergedIds);
          if (
            defaultIds.length > 0 &&
            (!chatConfig?.knowledgeBaseId ||
              chatConfig.knowledgeBaseId.length === 0)
          ) {
            onChange?.(
              mergedIds,
              chatConfig?.creators || [],
              chatConfig?.tags || [],
            );
          }
        })
        .finally(() => setKnowledgeLoading(false));
    }

    const filterKnowledgeBaseListFn = debounce((search: string) => {
      setSearchValue(search);
    }, 300);

    const sortedAndFilteredList = useMemo(() => {
      let list = [...knowledgeBaseList];

      if (searchValue.trim()) {
        list = list.filter((item) =>
          item.display_name?.toLowerCase().includes(searchValue.toLowerCase()),
        );
      }

      list.sort((a, b) => {
        const aSelected = selectedIds.includes(a.dataset_id || "");
        const bSelected = selectedIds.includes(b.dataset_id || "");

        if (aSelected && !bSelected) {
          return -1;
        }
        if (!aSelected && bSelected) {
          return 1;
        }

        return 0;
      });

      return list;
    }, [knowledgeBaseList, selectedIds, searchValue]);

    useEffect(() => {
      setFilteredList(sortedAndFilteredList);
    }, [sortedAndFilteredList]);

    function handleItemClick(datasetId?: string) {
      if (!datasetId) {
        return;
      }

      const newSelectedIds = selectedIds.includes(datasetId)
        ? selectedIds.filter((id) => id !== datasetId)
        : [...selectedIds, datasetId];

      setSelectedIds(newSelectedIds);
      onChange?.(
        newSelectedIds,
        form.getFieldValue("creators"),
        form.getFieldValue("tags"),
      );
    }

    function unSetDefaultDatasetFn(item: Dataset) {
      KnowledgeBaseServiceApi()
        .datasetServiceUnsetDefaultDataset({
          dataset: item?.dataset_id ?? "",
          unsetDefaultDatasetRequest: { name: item?.name ?? "" },
        })
        .then(() => {
          getKnowledgeBaseList();
        });
    }

    function setDefaultDatasetFn(item: Dataset) {
      KnowledgeBaseServiceApi()
        .datasetServiceSetDefaultDataset({
          dataset: item?.dataset_id ?? "",
          setDefaultDatasetRequest: { name: item?.name ?? "" },
        })
        .then(() => {
          getKnowledgeBaseList();
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
                      form.getFieldValue("creators") || [],
                      form.getFieldValue("tags") || [],
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
                    form.getFieldValue("creators"),
                    form.getFieldValue("tags"),
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
                    form.getFieldValue("creators"),
                    form.getFieldValue("tags"),
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
                  onClick={() => handleItemClick(item.dataset_id)}
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
          {renderConfigBottom()}
        </div>
      );
    }

    function renderConfigBottom() {
      return (
        <div className="chat-selectot-config">
          <div className="chat-select-config-header">
            <Space size={16}>
              <SettingOutlined />
              <span>{t("chat.docSettings")}</span>
              {showConfig && <Tag color="warning">{t("chat.enabled")}</Tag>}
            </Space>
            {showConfig ? (
              <UpOutlined onClick={() => setShowConfig(false)} />
            ) : (
              <DownOutlined onClick={() => setShowConfig(true)} />
            )}
          </div>
          {showConfig && (
            <>
              <Form.Item name="creators" style={{ marginBottom: 10 }}>
                <Select
                  mode="multiple"
                  tokenSeparators={[" "]}
                  onChange={(val) =>
                    onChange?.(selectedIds, val, form.getFieldValue("tags"))
                  }
                  allowClear
                  placeholder={t("chat.selectCreator")}
                  maxTagCount="responsive"
                  popupMatchSelectWidth
                  showSearch
                  filterOption={false}
                  options={creators.map((creator) => ({
                    value: creator.id,
                    label: creator.name,
                  }))}
                />
              </Form.Item>
              <Form.Item name="tags" style={{ marginBottom: 10 }}>
                <Select
                  mode="multiple"
                  tokenSeparators={[" "]}
                  onChange={(val) =>
                    onChange?.(selectedIds, form.getFieldValue("creators"), val)
                  }
                  allowClear
                  placeholder={t("chat.selectTag")}
                  maxTagCount="responsive"
                  popupMatchSelectWidth
                  showSearch
                  optionLabelProp="value"
                  filterOption={false}
                  options={tags.map((tag) => ({ value: tag, label: tag }))}
                />
              </Form.Item>
              <Button
                htmlType="button"
                type="link"
                onClick={() => form.resetFields()}
                style={{ padding: 0, marginBottom: 10 }}
              >
                {t("chat.reset")}
              </Button>
            </>
          )}
        </div>
      );
    }

    return (
      <Form form={form} component={false}>
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
      </Form>
    );
  },
);

export default ChatSelector;
