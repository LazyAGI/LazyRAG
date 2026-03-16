import { CommonModal } from "@/components/ui";
import { Switch, Space, message } from "antd";
import { useEffect, useState } from "react";
import { useConversationSettings } from "@/modules/chat/store/conversationSettings";
import { ChatServiceApi } from "@/modules/chat/utils/request";
import { useChatNewMessageStore } from "@/modules/chat/store/chatNewMessage";

interface ConversationSettingModalProps {
  cancelFn: () => void;
  initialStatus?: number; // 服务器返回的状态：1 = 开启，0 = 关闭
  onStatusChange?: () => void; // 状态变化后的回调
}

function ConversationSettingModal(props: ConversationSettingModalProps) {
  const { cancelFn, initialStatus, onStatusChange } = props;
  const { enableMultipleAnswers, setEnableMultipleAnswers } =
    useConversationSettings();
  const { newMessage } = useChatNewMessageStore();
  // 使用本地状态暂存用户的修改
  const [localEnableMultipleAnswers, setLocalEnableMultipleAnswers] = useState(
    enableMultipleAnswers,
  );

  // 当接收到初始状态时，同步到本地状态
  useEffect(() => {
    if (initialStatus !== undefined) {
      // 将数字转换为布尔值：1 -> true, 0 -> false
      const newValue = initialStatus === 1;
      setEnableMultipleAnswers(newValue);
      setLocalEnableMultipleAnswers(newValue);
    }
  }, [initialStatus, setEnableMultipleAnswers]);

  async function successFn() {
    try {
      // 将布尔值转换为接口需要的数字：true -> 1, false -> 0
      const status = localEnableMultipleAnswers ? 1 : 0;

      const response =
        await ChatServiceApi().conversationServiceSetMultiAnswersSwitchStatus({
          setMultiAnswersSwitchStatusRequest: {
            status,
          },
        });

      // 直接使用保存接口返回的状态更新 store，避免再次调用获取接口
      const savedStatus = response.data.status ?? status;
      setEnableMultipleAnswers(savedStatus === 1);
      // 非新建对话且改为单模型时，显示特殊提示
      if (!newMessage && savedStatus === 0) {
        message.success("后续回答将仍为 LazyRAG 大模型");
      } else {
        message.success("设置已保存");
      }
      // 如果父组件传入了回调，调用它来同步本地状态
      onStatusChange?.();
      cancelFn();
    } catch (error: any) {
      console.error("保存对话设置失败:", error);
      message.error(
        error?.response?.data?.message || "保存设置失败，请稍后重试",
      );
    }
  }

  function renderContent() {
    return (
      <div>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space>
            <span>生成两种不同的回答</span>
            <Switch
              checked={localEnableMultipleAnswers}
              onChange={(val) => {
                setLocalEnableMultipleAnswers(val);
              }}
            />
          </Space>
          <div style={{ fontSize: 12, color: "#8d9ab2" }}>
            开启后，当两种模型回答差距较大时，会展示多个回答供您选择
          </div>
        </Space>
      </div>
    );
  }

  return (
    <CommonModal
      contentText={renderContent()}
      title="对话设置"
      cancelFn={cancelFn}
      successFn={successFn}
    />
  );
}

export default ConversationSettingModal;
