
import { Button, Input } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AgentAppsAuth } from "@/components/auth";

export default function ChatPage() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20 }}>{t("chat.knowledgeQA")}</h1>
        <Button
          type="link"
          onClick={() => {
            AgentAppsAuth.logout();
          }}
        >
          {t("chat.exit")}
        </Button>
      </div>
      <p style={{ color: "#666", marginBottom: 16 }}>
        {t("chat.inputPlaceholder")}
      </p>
      <Input.TextArea
        placeholder={t("chat.inputPlaceholder")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={3}
        style={{ marginBottom: 16 }}
      />
      <Button type="primary">{t("chat.send")}</Button>
    </div>
  );
}
