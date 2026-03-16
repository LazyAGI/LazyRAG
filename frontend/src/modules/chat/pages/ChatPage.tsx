/**
 * Chat 问答模块 - LazyRAG 知识问答
 * 完整 UI 可从 tieyiyuan apps/chat 迁移：拷贝 NewChatPage、newChatContainer、ChatInput 等，
 * 并将 @repo/shared-openapi 改为 @/api/generated，@repo/shared-* 改为 @/components。
 */
import { Button, Input } from "antd";
import { useState } from "react";
import { AgentAppsAuth } from "@/components/auth";

export default function ChatPage() {
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
        <h1 style={{ margin: 0, fontSize: 20 }}>知识问答</h1>
        <Button
          type="link"
          onClick={() => {
            AgentAppsAuth.logout();
          }}
        >
          退出
        </Button>
      </div>
      <p style={{ color: "#666", marginBottom: 16 }}>
        请输入您的问题，支持多轮对话、图文理解等
      </p>
      <Input.TextArea
        placeholder="请输入您的问题，支持多轮对话、图文理解等"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={3}
        style={{ marginBottom: 16 }}
      />
      <Button type="primary">发送</Button>
    </div>
  );
}
