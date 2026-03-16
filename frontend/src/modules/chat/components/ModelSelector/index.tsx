import { useState } from "react";
import { Dropdown, message } from "antd";
import { DownOutlined, CheckOutlined } from "@ant-design/icons";
import {
  useModelSelectionStore,
  MODEL_LABELS,
  MODEL_OPTIONS,
  type ModelSelectionType,
} from "@/modules/chat/store/modelSelection";
import "./index.scss";

interface ModelSelectorProps {
  sessionId?: string;
  disabled?: boolean; // 流式输出时禁用
}

function ModelSelector({
  sessionId = "",
  disabled = false,
}: ModelSelectorProps) {
  const { getModelSelection, setModelSelection } = useModelSelectionStore();
  const [open, setOpen] = useState(false);

  const currentSelection = getModelSelection(sessionId);

  const getDisplayText = () => {
    return MODEL_LABELS[currentSelection];
  };

  const handleOptionClick = (value: "value_engineering" | "deepseek") => {
    const isValueEng = value === "value_engineering";

    const hasValueEng =
      currentSelection === "value_engineering" || currentSelection === "both";
    const hasDeepSeek =
      currentSelection === "deepseek" || currentSelection === "both";

    let newSelection: ModelSelectionType;

    if (isValueEng) {
      if (hasValueEng && hasDeepSeek) {
        // 当前双选，点击 LazyRAG -> 取消 LazyRAG，只剩 DeepSeek
        newSelection = "deepseek";
      } else if (hasValueEng && !hasDeepSeek) {
        // 当前只有 LazyRAG，点击 -> 阻止（至少选一个）
        message.warning("至少选择一个模型");
        return;
      } else {
        // 当前只有 DeepSeek，点击 LazyRAG -> 双选
        newSelection = "both";
      }
    } else {
      // isDeepSeek
      if (hasValueEng && hasDeepSeek) {
        // 当前双选，点击 DeepSeek -> 取消 DeepSeek，只剩 LazyRAG
        newSelection = "value_engineering";
      } else if (!hasValueEng && hasDeepSeek) {
        // 当前只有 DeepSeek，点击 -> 阻止
        message.warning("至少选择一个模型");
        return;
      } else {
        // 当前只有 LazyRAG，点击 DeepSeek -> 双选
        newSelection = "both";
      }
    }

    setModelSelection(sessionId, newSelection);
  };

  const getCheckState = (value: "value_engineering" | "deepseek") => {
    if (value === "value_engineering") {
      return (
        currentSelection === "value_engineering" || currentSelection === "both"
      );
    }
    return currentSelection === "deepseek" || currentSelection === "both";
  };

  const dropdownContent = (
    <div className="model-selector-dropdown">
      {MODEL_OPTIONS.map((opt) => (
        <div
          key={opt.value}
          className="model-selector-option"
          onClick={() => handleOptionClick(opt.value)}
        >
          <div className="model-selector-option-main">
            <span className="model-selector-label">{opt.label}</span>
            <span className="model-selector-check">
              {getCheckState(opt.value) ? (
                <CheckOutlined style={{ color: "rgba(0, 106, 230, 1)" }} />
              ) : null}
            </span>
          </div>
          <div className="model-selector-desc">{opt.description}</div>
        </div>
      ))}
    </div>
  );

  return (
    <Dropdown
      popupRender={() => dropdownContent}
      trigger={["click"]}
      open={open}
      onOpenChange={(visible) => !disabled && setOpen(visible)}
      disabled={disabled}
    >
      <div className={`model-selector-trigger ${disabled ? "disabled" : ""}`}>
        <span className="model-selector-text">{getDisplayText()}</span>
        <DownOutlined className="model-selector-arrow" />
      </div>
    </Dropdown>
  );
}

export default ModelSelector;
