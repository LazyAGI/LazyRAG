import "./index.scss";

const CURRENT_ENV_TITLE =
  import.meta.env.VITE_APP_CHAT_TITLE ||
  "LazyRAG —— 让知识“即问即答” ✨🔮";

const InitialCard = () => {
  const infoList = [
    {
      icon: "💬",
      title: "智能对话交互",
      text: "基于前沿大模型，深度融合私有知识，提供精准的多轮上下文理解能力。",
    },
    {
      icon: "📚",
      title: "全源知识集成",
      text: "支持从知识库、结构化/非结构化文档的深度融合，构建企业专属知识大脑。",
    },
    {
      icon: "📈",
      title: "闭环反馈优化",
      text: "支持用户反馈与点赞点踩机制，通过真实对话数据持续迭代问答质量。",
    },
    {
      icon: "🛠️",
      title: "即插即用接入",
      text: "提供低代码操作平台与标准 API 接口，分钟级集成至现有业务系统。",
    },
    {
      icon: "🔐",
      title: "安全协作管控",
      text: "完善的角色权限隔离与数据分级管理，确保企业核心资产安全高效共享。",
    },
  ];

  return (
    <div className="chat-initial-card">
      <div className="chat-initial-card-title">{CURRENT_ENV_TITLE}</div>
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
