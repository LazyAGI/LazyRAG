import "./index.scss";
import { useTranslation } from "react-i18next";

const CURRENT_ENV_TITLE =
  import.meta.env.VITE_APP_CHAT_TITLE || "";

const InitialCard = () => {
  const { t } = useTranslation();
  const title = CURRENT_ENV_TITLE || t("chat.initialTitle");

  const infoList = [
    { icon: "💬", title: t("chat.feature1Title"), text: t("chat.feature1Text") },
    { icon: "📚", title: t("chat.feature2Title"), text: t("chat.feature2Text") },
    { icon: "📈", title: t("chat.feature3Title"), text: t("chat.feature3Text") },
    { icon: "🛠️", title: t("chat.feature4Title"), text: t("chat.feature4Text") },
    { icon: "🔐", title: t("chat.feature5Title"), text: t("chat.feature5Text") },
  ];

  return (
    <div className="chat-initial-card">
      <div className="chat-initial-card-title">{title}</div>
      {infoList.map((item, index) => {
        return (
          <div className="chat-initial-info-item" key={index}>
            {item.icon}
            {item.title && (
              <span className="chat-initial-info-title">{item.title}</span>
            )}
            <div>{item.text}</div>
          </div>
        );
      })}
    </div>
  );
};

export default InitialCard;
