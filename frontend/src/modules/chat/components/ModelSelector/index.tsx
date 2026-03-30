import { useState } from "react";
import { Dropdown, message } from "antd";
import { useTranslation } from "react-i18next";
import { DownOutlined, CheckOutlined } from "@ant-design/icons";
import {
  useModelSelectionStore,
  MODEL_SELECTION_SUMMARY_KEYS,
  MODEL_OPTIONS,
  type ModelSelectionType,
} from "@/modules/chat/store/modelSelection";
import "./index.scss";

interface ModelSelectorProps {
  sessionId?: string;
  disabled?: boolean;
}

function ModelSelector({
  sessionId = "",
  disabled = false,
}: ModelSelectorProps) {
  const { t } = useTranslation();
  const { getModelSelection, setModelSelection } = useModelSelectionStore();
  const [open, setOpen] = useState(false);

  const currentSelection = getModelSelection(sessionId);

  const getDisplayText = () => {
    return t(MODEL_SELECTION_SUMMARY_KEYS[currentSelection]);
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
        newSelection = "deepseek";
      } else if (hasValueEng && !hasDeepSeek) {
        message.warning(t("chat.chooseAtLeastOneModel"));
        return;
      } else {
        newSelection = "both";
      }
    } else {
      // isDeepSeek
      if (hasValueEng && hasDeepSeek) {
        newSelection = "value_engineering";
      } else if (!hasValueEng && hasDeepSeek) {
        message.warning(t("chat.chooseAtLeastOneModel"));
        return;
      } else {
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
            <span className="model-selector-label">{t(opt.labelKey)}</span>
            <span className="model-selector-check">
              {getCheckState(opt.value) ? (
                <CheckOutlined style={{ color: "rgba(0, 106, 230, 1)" }} />
              ) : null}
            </span>
          </div>
          <div className="model-selector-desc">{t(opt.descriptionKey)}</div>
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
