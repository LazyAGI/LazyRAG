/**
 * 全局流管理器
 * 管理所有会话的流，支持多流同时输出，切换会话时流不中断
 */

import { SSE } from "./sse";

export interface StreamCallbacks {
  message?: (e: CustomEvent) => void;
  error?: (e: CustomEvent) => void;
  timeout?: (e: CustomEvent) => void;
}

export interface StreamState {
  conversationId: string;
  delta: string;
  reasoning_content: string;
  sources?: any[];
  finish_reason?: string;
  messageId?: string;
  history_id?: string;
  // 保存完整的消息列表，包括用户的问题和助手的部分回答
  messageList?: any[];
}

/**
 * 流管理器单例
 * 管理所有会话的流，一个会话最多一个流（一对一关系）
 */
class StreamManager {
  private streams: Map<string, SSE> = new Map(); // conversationId -> SSE实例
  private callbacks: Map<string, StreamCallbacks> = new Map(); // conversationId -> 回调函数
  private streamStates: Map<string, StreamState> = new Map(); // conversationId -> 流状态
  private activeConversationId: string | null = null; // 当前活跃的会话ID

  /**
   * 注册流
   * @param conversationId 会话ID
   * @param sse SSE实例
   * @param callbacks 回调函数
   */
  registerStream(
    conversationId: string,
    sse: SSE,
    callbacks: StreamCallbacks,
  ): void {
    // 如果该会话已有流，先清理旧的（包括移除监听器）
    const existingStream = this.streams.get(conversationId);
    if (existingStream) {
      // 先清理监听器，再关闭流
      const oldCallbacks = this.callbacks.get(conversationId);
      if (oldCallbacks) {
        if (oldCallbacks.message) {
          existingStream.removeEventListener("message", oldCallbacks.message);
        }
        if (oldCallbacks.error) {
          existingStream.removeEventListener("error", oldCallbacks.error);
        }
        if (oldCallbacks.timeout) {
          existingStream.removeEventListener("timeout", oldCallbacks.timeout);
        }
      }
      existingStream.close();
    }

    // 注册新的流
    this.streams.set(conversationId, sse);
    this.callbacks.set(conversationId, callbacks);

    // 初始化流状态（如果不存在）
    if (!this.streamStates.has(conversationId)) {
      this.streamStates.set(conversationId, {
        conversationId,
        delta: "",
        reasoning_content: "",
        sources: undefined,
        finish_reason: undefined,
        messageId: undefined,
        history_id: undefined,
      });
    } else {
      // 如果状态已存在，重置delta和reasoning_content（新流开始）
      const existingState = this.streamStates.get(conversationId);
      if (existingState) {
        existingState.delta = "";
        existingState.reasoning_content = "";
        existingState.finish_reason = undefined;
      }
    }

    // 设置包装的回调函数，用于更新流状态
    // 使用闭包保存conversationId，确保回调函数只处理属于该会话的消息
    const wrappedCallbacks: StreamCallbacks = {
      message: (e: CustomEvent) => {
        // 首先检查消息的conversation_id是否匹配（如果消息中有conversation_id）
        try {
          const data = (e as any).data;
          if (typeof data === "string") {
            // 检查是否是流结束标记
            if (data.trim() === "[DONE]") {
              return;
            }
            const parsed = JSON.parse(data);
            const result = parsed?.result;
            // 验证消息的conversation_id是否匹配
            // 如果当前使用的是临时ID（以temp_开头），允许接受服务器返回的任何conversation_id
            const isTempId = conversationId.startsWith("temp_");
            if (
              result?.conversation_id &&
              result.conversation_id !== conversationId &&
              !isTempId
            ) {
              // 消息的conversation_id与注册的conversationId不匹配，忽略
              return;
            }
          }
        } catch {
          // 解析失败，继续处理
        }

        // 更新流状态
        this.updateStreamState(conversationId, e);
        // 关键修复：无论是否为活跃会话，都调用回调
        // ChatContainer的onMessage会根据isActiveConversation判断是更新UI还是只更新缓存
        if (callbacks.message) {
          callbacks.message(e);
        }
      },
      error: (e: CustomEvent) => {
        // 错误也要通知，让ChatContainer处理
        if (callbacks.error) {
          callbacks.error(e);
        }
        // 错误时清理流
        this.cleanupStream(conversationId);
      },
      timeout: (e: CustomEvent) => {
        // 超时也要通知，让ChatContainer处理
        if (callbacks.timeout) {
          callbacks.timeout(e);
        }
        // 超时时清理流
        this.cleanupStream(conversationId);
      },
    };

    // 更新回调
    this.callbacks.set(conversationId, wrappedCallbacks);

    // 为SSE添加事件监听器
    if (wrappedCallbacks.message) {
      sse.addEventListener("message", wrappedCallbacks.message);
    }
    if (wrappedCallbacks.error) {
      sse.addEventListener("error", wrappedCallbacks.error);
    }
    if (wrappedCallbacks.timeout) {
      sse.addEventListener("timeout", wrappedCallbacks.timeout);
    }
  }

  /**
   * 更新流状态
   */
  private updateStreamState(conversationId: string, e: CustomEvent): void {
    // 确保状态存在，如果不存在则初始化
    if (!this.streamStates.has(conversationId)) {
      this.streamStates.set(conversationId, {
        conversationId,
        delta: "",
        reasoning_content: "",
        sources: undefined,
        finish_reason: undefined,
        messageId: undefined,
        history_id: undefined,
      });
    }

    const state = this.streamStates.get(conversationId);
    if (!state) {
      return;
    }

    try {
      const data = (e as any).data;
      if (typeof data === "string") {
        // 检查是否是流结束标记，如果是则直接返回
        if (data.trim() === "[DONE]") {
          return;
        }
        const parsed = JSON.parse(data);
        const result = parsed?.result;
        if (result) {
          // 重要：这里不累加delta和reasoning_content，只保存最新的增量值
          // 累加由ChatContainer的onMessage负责，避免重复累加导致内容重复
          // StreamManager只负责保存状态元数据（sources, finish_reason等）
          // 恢复时优先使用messageList（已在ChatContainer中累加好的完整内容）
          if (result.sources && result.sources.length > 0) {
            state.sources = result.sources;
          }
          if (result.finish_reason) {
            state.finish_reason = result.finish_reason;
          }
          if (result.messageId) {
            state.messageId = result.messageId;
          }
          if (result.history_id) {
            state.history_id = result.history_id;
          }
          if (result.conversation_id) {
            state.conversationId = result.conversation_id;
          }
          // 注意：不更新delta和reasoning_content，避免重复累加
          // 这些值由ChatContainer负责累加和保存到messageList中
        }
      }
    } catch (error) {
      console.error("Failed to parse stream data:", error);
    }
  }

  /**
   * 设置当前活跃的会话
   * @param conversationId 会话ID
   */
  setActiveConversation(conversationId: string | null): void {
    this.activeConversationId = conversationId;
  }

  /**
   * 获取流的当前状态
   * @param conversationId 会话ID
   * @returns 流状态，如果不存在则返回null
   */
  getStreamState(conversationId: string): StreamState | null {
    return this.streamStates.get(conversationId) || null;
  }

  /**
   * 保存消息列表到流状态（用于切换会话时保存当前状态）
   * @param conversationId 会话ID
   * @param messageList 消息列表
   */
  saveMessageList(conversationId: string, messageList: any[]): void {
    const state = this.streamStates.get(conversationId);
    if (state) {
      state.messageList = messageList;
    } else {
      // 如果状态不存在，创建新状态
      this.streamStates.set(conversationId, {
        conversationId,
        delta: "",
        reasoning_content: "",
        messageList,
      });
    }
  }

  /**
   * 检查会话是否有活跃的流
   * @param conversationId 会话ID
   * @returns 是否有活跃的流
   */
  hasActiveStream(conversationId: string): boolean {
    const stream = this.streams.get(conversationId);
    if (!stream) {
      return false;
    }
    // 检查流是否还在运行（readyState: 0=CONNECTING, 1=OPEN）
    return stream.readyState === 0 || stream.readyState === 1;
  }

  /**
   * 获取流的SSE实例
   * @param conversationId 会话ID
   * @returns SSE实例，如果不存在则返回null
   */
  getStream(conversationId: string): SSE | null {
    return this.streams.get(conversationId) || null;
  }

  /**
   * 获取流的回调函数
   * @param conversationId 会话ID
   * @returns 回调函数，如果不存在则返回null
   */
  getCallbacks(conversationId: string): StreamCallbacks | null {
    return this.callbacks.get(conversationId) || null;
  }

  /**
   * 关闭指定会话的流
   * @param conversationId 会话ID
   */
  closeStream(conversationId: string): void {
    const stream = this.streams.get(conversationId);
    if (stream) {
      stream.close();
    }
    this.cleanupStream(conversationId);
  }

  /**
   * 清理流（不关闭连接，只清理本地状态）
   * @param conversationId 会话ID
   */
  private cleanupStream(conversationId: string): void {
    const stream = this.streams.get(conversationId);
    if (stream) {
      // 移除事件监听器
      const callbacks = this.callbacks.get(conversationId);
      if (callbacks) {
        try {
          if (callbacks.message) {
            stream.removeEventListener("message", callbacks.message);
          }
          if (callbacks.error) {
            stream.removeEventListener("error", callbacks.error);
          }
          if (callbacks.timeout) {
            stream.removeEventListener("timeout", callbacks.timeout);
          }
        } catch (error) {
          // 如果移除监听器失败（流可能已关闭），继续执行
          console.warn(
            "Failed to remove event listeners during cleanup:",
            error,
          );
        }
      }
    }

    // 如果流已完成，清理状态
    const state = this.streamStates.get(conversationId);
    if (state?.finish_reason) {
      this.streams.delete(conversationId);
      this.callbacks.delete(conversationId);
      // 保留流状态一段时间，以便切换时恢复显示
      // 可以设置一个定时器来清理旧状态，这里暂时保留
    }
  }

  /**
   * 检查流是否已完成（有finish_reason且不是UNSPECIFIED）
   * @param conversationId 会话ID
   * @returns 流是否已完成
   */
  isStreamFinished(conversationId: string): boolean {
    const state = this.streamStates.get(conversationId);
    if (!state || !state.finish_reason) {
      return false;
    }
    // FINISH_REASON_UNSPECIFIED 表示流还在进行中
    return state.finish_reason !== "FINISH_REASON_UNSPECIFIED";
  }

  /**
   * 彻底清理指定会话的所有数据（关闭流、移除所有状态和缓存）
   * @param conversationId 会话ID
   */
  closeAndCleanup(conversationId: string): void {
    // 1. 关闭SSE连接
    const stream = this.streams.get(conversationId);
    if (stream) {
      try {
        // 先移除事件监听器
        const callbacks = this.callbacks.get(conversationId);
        if (callbacks) {
          if (callbacks.message) {
            stream.removeEventListener("message", callbacks.message);
          }
          if (callbacks.error) {
            stream.removeEventListener("error", callbacks.error);
          }
          if (callbacks.timeout) {
            stream.removeEventListener("timeout", callbacks.timeout);
          }
        }
        // 关闭连接
        stream.close();
      } catch (error) {
        console.error("[StreamManager] 关闭流失败:", error);
      }
    }

    // 2. 清理所有状态
    this.streams.delete(conversationId);
    this.callbacks.delete(conversationId);
    this.streamStates.delete(conversationId);

    // 3. 如果这是当前活跃会话，清除活跃状态
    if (this.activeConversationId === conversationId) {
      this.activeConversationId = null;
    }
  }

  /**
   * 清理指定会话的流状态（用于手动清理）
   * @param conversationId 会话ID
   */
  clearStreamState(conversationId: string): void {
    this.streamStates.delete(conversationId);
  }

  /**
   * 从streams和callbacks Map中删除指定会话的条目（不关闭连接，不移除监听器）
   * @param conversationId 会话ID
   */
  removeStreamEntry(conversationId: string): void {
    this.streams.delete(conversationId);
    this.callbacks.delete(conversationId);
  }

  /**
   * 恢复流的回调（当切换回会话时）
   * @param conversationId 会话ID
   * @param callbacks 新的回调函数
   */
  restoreStreamCallbacks(
    conversationId: string,
    callbacks: StreamCallbacks,
  ): void {
    const stream = this.streams.get(conversationId);
    if (!stream) {
      return;
    }

    // 检查流是否还在运行
    if (stream.readyState === 2) {
      // 流已关闭，清理状态
      this.cleanupStream(conversationId);
      return;
    }

    // 移除旧的回调
    const oldCallbacks = this.callbacks.get(conversationId);
    if (oldCallbacks) {
      try {
        if (oldCallbacks.message) {
          stream.removeEventListener("message", oldCallbacks.message);
        }
        if (oldCallbacks.error) {
          stream.removeEventListener("error", oldCallbacks.error);
        }
        if (oldCallbacks.timeout) {
          stream.removeEventListener("timeout", oldCallbacks.timeout);
        }
      } catch (error) {
        // 如果移除监听器失败（流可能已关闭），继续执行
        console.warn("Failed to remove event listeners:", error);
      }
    }

    // 设置新的回调
    const wrappedCallbacks: StreamCallbacks = {
      message: (e: CustomEvent) => {
        // 首先检查消息的conversation_id是否匹配（如果消息中有conversation_id）
        try {
          const data = (e as any).data;
          if (typeof data === "string") {
            // 检查是否是流结束标记
            if (data.trim() === "[DONE]") {
              return;
            }
            const parsed = JSON.parse(data);
            const result = parsed?.result;
            // 验证消息的conversation_id是否匹配
            // 如果当前使用的是临时ID（以temp_开头），允许接受服务器返回的任何conversation_id
            const isTempId = conversationId.startsWith("temp_");
            if (
              result?.conversation_id &&
              result.conversation_id !== conversationId &&
              !isTempId
            ) {
              // 消息的conversation_id与注册的conversationId不匹配，忽略
              return;
            }
          }
        } catch {
          // 解析失败，继续处理
        }

        this.updateStreamState(conversationId, e);
        // 关键修复：无论是否为活跃会话，都调用回调
        if (callbacks.message) {
          callbacks.message(e);
        }
      },
      error: (e: CustomEvent) => {
        // 错误也要通知
        if (callbacks.error) {
          callbacks.error(e);
        }
        this.cleanupStream(conversationId);
      },
      timeout: (e: CustomEvent) => {
        // 超时也要通知
        if (callbacks.timeout) {
          callbacks.timeout(e);
        }
        this.cleanupStream(conversationId);
      },
    };

    this.callbacks.set(conversationId, wrappedCallbacks);

    // 添加新的事件监听器
    if (wrappedCallbacks.message) {
      stream.addEventListener("message", wrappedCallbacks.message);
    }
    if (wrappedCallbacks.error) {
      stream.addEventListener("error", wrappedCallbacks.error);
    }
    if (wrappedCallbacks.timeout) {
      stream.addEventListener("timeout", wrappedCallbacks.timeout);
    }
  }

  /**
   * 获取所有活跃的会话ID
   * @returns 活跃的会话ID数组
   */
  getActiveConversationIds(): string[] {
    return Array.from(this.streams.keys()).filter((id) =>
      this.hasActiveStream(id),
    );
  }

  /**
   * 清理所有已完成的流（批量清理）
   * 适用于定期清理或内存优化场景
   */
  cleanupFinishedStreams(): void {
    const finishedIds: string[] = [];

    // 找出所有已完成的会话
    this.streamStates.forEach((_state, conversationId) => {
      if (this.isStreamFinished(conversationId)) {
        finishedIds.push(conversationId);
      }
    });

    if (finishedIds.length > 0) {
      finishedIds.forEach((id) => {
        this.closeAndCleanup(id);
      });
    }
  }

  /**
   * 获取所有会话的状态信息（用于调试）
   */
  getDebugInfo(): any {
    const info: any = {
      activeConversationId: this.activeConversationId,
      totalStreams: this.streams.size,
      totalStates: this.streamStates.size,
      streams: {},
    };

    this.streamStates.forEach((state, conversationId) => {
      info.streams[conversationId] = {
        isActive: this.hasActiveStream(conversationId),
        isFinished: this.isStreamFinished(conversationId),
        finish_reason: state.finish_reason,
        messageListLength: state.messageList?.length || 0,
      };
    });

    return info;
  }
}

// 导出单例
export const streamManager = new StreamManager();
