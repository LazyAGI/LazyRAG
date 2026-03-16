import { CloseOutlined, CloudDownloadOutlined } from "@ant-design/icons";
import classnames from "classnames";
import {
  Button,
  Checkbox,
  Col,
  Input,
  message,
  Row,
  Spin,
  Tooltip,
} from "antd";
import {
  Conversation,
  ExportConversationsRequestFileTypesEnum,
} from "@/api/generated/chatbot-client";
import { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { useState } from "react";
import InfiniteScroll from "react-infinite-scroll-component";
import { useChatThinkStore } from "@/modules/chat/store/chatThink";
import { useChatNewMessageStore } from "@/modules/chat/store/chatNewMessage";

import dayjs from "dayjs";

import { ChatServiceApi } from "@/modules/chat/utils/request";
import "./index.scss";
import { downloadUrl } from "@/modules/chat/utils/download";

interface IRecordList {
  currentSessionId: string;
  onSelected: (props: Conversation) => void;
  onRemove: (props: Conversation) => void;
}

export interface RecordListImperativeProps {
  refresh: () => void;
}

const { Search } = Input;

const RecordList = forwardRef<RecordListImperativeProps, IRecordList>(
  (props, ref) => {
    const { currentSessionId, onSelected, onRemove } = props;
    const [historyList, setHistoryList] = useState<Conversation[]>([]);
    const [keyword, setKeyword] = useState("");
    const [pageToken, setPageToken] = useState("");
    const [checkedList, setCheckedList] = useState<string[]>([]);
    const [showBatchExport, setShowBatchExport] = useState(false);
    const listRef = useRef(null);
    const { setThink } = useChatThinkStore();
    const { setNewMessage } = useChatNewMessageStore();
    useImperativeHandle(ref, () => ({
      refresh: () => {
        getHistory({ isFirst: true });
      },
    }));

    useEffect(() => {
      // 如果当前会话 ID 不在历史列表中，则重新获取历史记录，新建会话时会触发此逻辑。
      if (
        !historyList?.some(
          (history) => history.conversation_id === currentSessionId,
        )
      ) {
        getHistory({ isFirst: true });
      }
    }, [currentSessionId]);

    function getHistory(params?: {
      isMore?: boolean;
      isFirst?: boolean;
      searchText?: string;
    }) {
      const { isMore = false, isFirst = false, searchText } = params ?? {};
      ChatServiceApi()
        .conversationServiceListConversations({
          keyword: searchText ?? keyword,
          pageToken: isFirst ? "" : pageToken,
          pageSize: 50,
        })
        .then((res) => {
          const conversations: Conversation[] = res?.data?.conversations ?? [];
          setHistoryList(
            isMore
              ? [...(historyList || []), ...(conversations || [])]
              : conversations,
          );
          setPageToken(res.data.next_page_token || "");
        });
    }

    function deleteHistory(data: Conversation) {
      ChatServiceApi()
        .conversationServiceDeleteConversation({
          conversation: data.conversation_id || "",
        })
        .then(() => {
          message.success("删除会话成功");
          getHistory({ isFirst: true });
          if (listRef.current) {
            listRef.current.el.scrollTo({ top: 0 });
          }
        });
      onRemove(data);
    }

    function exportHistoryFn() {
      ChatServiceApi()
        .conversationServiceExportConversations({
          exportConversationsRequest: {
            conversation_ids: checkedList,
            file_types: [
              ExportConversationsRequestFileTypesEnum.ExportFileTypeXlsx,
            ],
          },
        })
        .then((res) => {
          const { uris = [] } = res.data;
          if (uris?.length) {
            downloadUrl(uris[0]);
          } else {
            message.warning("没有可导出的会话记录");
          }
        })
        .finally(() => {
          setCheckedList([]);
        });
    }

    function renderItemText(params: { item: Conversation; selected: boolean }) {
      const { item, selected } = params;
      return (
        <div
          className={classnames("record", { selected })}
          key={item.conversation_id}
          onClick={(e) => {
            e.preventDefault();
            if (selected) {
              return;
            }
            onSelected(item);
            setThink(false);
            setNewMessage(false);
          }}
        >
          <Tooltip title={item.display_name}>
            <span className="title">{item.display_name}</span>
          </Tooltip>
          <span className="update-time">
            {dayjs(item.update_time).format("MM/DD")}
          </span>
          <CloseOutlined
            className="close"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              deleteHistory(item);
            }}
          />
        </div>
      );
    }

    function renderItem() {
      return (
        <Row>
          {historyList?.map((item) => {
            const selected = item.conversation_id === currentSessionId;
            return (
              <Col span={24} key={item.conversation_id}>
                {showBatchExport ? (
                  <Checkbox
                    className="export-checkbox-item"
                    value={item.conversation_id}
                  >
                    {renderItemText({ item, selected })}
                  </Checkbox>
                ) : (
                  renderItemText({ item, selected })
                )}
              </Col>
            );
          })}
        </Row>
      );
    }

    return (
      <div className="record-container">
        <div className="list-title">会话历史</div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
          }}
        >
          <Search
            placeholder="搜索对话"
            allowClear
            onSearch={(value: string) => {
              getHistory({ searchText: value, isFirst: true });
              setKeyword(value);
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            {showBatchExport ? (
              <>
                <Button
                  type="link"
                  icon={<CloudDownloadOutlined />}
                  onClick={() => {
                    if (checkedList?.length) {
                      exportHistoryFn();
                    } else {
                      message.warning("请先选择要导出的会话");
                    }
                  }}
                >
                  导出
                </Button>
                <Button type="text" onClick={() => setShowBatchExport(false)}>
                  取消
                </Button>
              </>
            ) : (
              <Button
                type="link"
                style={{ padding: 0 }}
                onClick={() => setShowBatchExport(true)}
              >
                批量
              </Button>
            )}
          </div>
        </div>
        {showBatchExport && (
          <div style={{ padding: "8px 0" }}>
            <Checkbox
              indeterminate={
                checkedList?.length > 0 &&
                checkedList.length < historyList?.length
              }
              checked={
                historyList?.length === checkedList?.length &&
                !!checkedList?.length
              }
              onChange={(e) =>
                setCheckedList(
                  e.target.checked
                    ? historyList?.map((it) => it?.conversation_id ?? "")
                    : [],
                )
              }
            >
              全选
            </Checkbox>
          </div>
        )}
        <div className="record-list" id="scrollableDiv">
          <InfiniteScroll
            dataLength={historyList?.length || 0}
            next={() => getHistory({ isMore: true })}
            hasMore={!!pageToken}
            loader={<Spin />}
            ref={listRef}
            scrollableTarget="scrollableDiv"
          >
            {showBatchExport ? (
              <Checkbox.Group
                className="export-checkbox-group"
                onChange={(list) => setCheckedList(list)}
                value={checkedList}
              >
                {renderItem()}
              </Checkbox.Group>
            ) : (
              renderItem()
            )}
          </InfiniteScroll>
        </div>
      </div>
    );
  },
);

export default RecordList;
