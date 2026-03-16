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
          // 如果存在默认知识库且 chatConfig 中没有知识库配置，自动调用 onChange 通知父组件
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

    // 使用 useMemo 计算排序后的列表
    const sortedAndFilteredList = useMemo(() => {
      let list = [...knowledgeBaseList];

      // 先进行搜索过滤
      if (searchValue.trim()) {
        list = list.filter((item) =>
          item.display_name?.toLowerCase().includes(searchValue.toLowerCase()),
        );
      }

      // 然后进行排序：已选中的置顶
      list.sort((a, b) => {
        const aSelected = selectedIds.includes(a.dataset_id || "");
        const bSelected = selectedIds.includes(b.dataset_id || "");

        // 已选中的排在前面
        if (aSelected && !bSelected) {
          return -1;
        }
        if (!aSelected && bSelected) {
          return 1;
        }

        // 如果都选中或都未选中，保持原有顺序
        return 0;
      });

      return list;
    }, [knowledgeBaseList, selectedIds, searchValue]);

    // 更新 filteredList
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
              placeholder="搜索知识库"
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
                // 重置默认知识库后，同时取消临时选中（仅保留默认知识库）
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
              重置
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
                全选
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
                取消全选
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
              <div className="chat-selector-empty-text">加载中,请稍后...</div>
            ) : !filteredList?.length ? (
              <div className="chat-selector-empty-text">暂无数据</div>
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
              <span>文档设置</span>
              {showConfig && <Tag color="warning">启用</Tag>}
            </Space>
            {showConfig ? (
              <UpOutlined onClick={() => setShowConfig(false)} />
            ) : (
              <DownOutlined onClick={() => setShowConfig(true)} />
            )}
          </div>
          {showConfig && (
            <Form form={form} layout="vertical">
              <Form.Item name="creators" style={{ marginBottom: 10 }}>
                <Select
                  mode="multiple"
                  tokenSeparators={[" "]}
                  onChange={(val) =>
                    onChange?.(selectedIds, val, form.getFieldValue("tags"))
                  }
                  allowClear
                  placeholder="请选择文档创建人"
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
                  placeholder="请选择文档标签"
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
                重置
              </Button>
            </Form>
          )}
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
            知识库
          </div>
        </Popover>
      </div>
    );
  },
);

export default ChatSelector;
