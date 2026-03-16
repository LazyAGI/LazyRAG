import {
  Configuration,
  ConversationServiceApiFactory,
  PromptServiceApiFactory,
  FileServiceApiFactory as ChatFileServiceApiFactory,
} from "@/api/generated/chatbot-client";
import {
  DocumentServiceApiFactory,
  DatasetServiceApiFactory,
  DatabaseServiceApiFactory,
} from "@/api/generated/knowledge-client";
import { FileServiceApiFactory } from "@/api/generated/file-client";
import { axiosInstance, BASE_URL } from "@/components/request";

const baseUrl = `${BASE_URL}/api`;

axiosInstance.defaults.timeout = 60 * 1000; // 10 seconds

const Config = new Configuration();

export function ChatServiceApi() {
  return ConversationServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function PromptServiceApi() {
  return PromptServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function DocumentServiceApi() {
  return DocumentServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function KnowledgeBaseServiceApi() {
  return DatasetServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function FileServiceApi() {
  return FileServiceApiFactory(Config, `${baseUrl}/fileservice`, axiosInstance);
}

export function DatabaseBaseServiceApi() {
  return DatabaseServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function ChatFileServiceApi() {
  return ChatFileServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}
