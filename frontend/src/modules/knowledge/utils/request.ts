import {
  Configuration,
  DatasetServiceApiFactory,
  DocumentServiceApiFactory,
  DatasetMemberServiceApiFactory,
  JobServiceApiFactory,
  SegmentServiceApiFactory,
} from "@/api/generated/knowledge-client";
import {
  UsersApiFactory,
  GroupsApiFactory,
} from "@/api/generated/authservice-client";
import { axiosInstance, BASE_URL } from "@/components/request";

const baseUrl = `${BASE_URL}/api`;

axiosInstance.defaults.timeout = 60 * 1000; // 60 seconds

const Config = new Configuration();

export function KnowledgeBaseServiceApi() {
  return DatasetServiceApiFactory(
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

export function MemberServiceApi() {
  return DatasetMemberServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function JobServiceApi() {
  return JobServiceApiFactory(Config, `${baseUrl}/ragservice`, axiosInstance);
}

export function SegmentServiceApi() {
  return SegmentServiceApiFactory(
    Config,
    `${baseUrl}/ragservice`,
    axiosInstance,
  );
}

export function UsersServiceApi() {
  return UsersApiFactory(Config, `${baseUrl}/authservice/v1`, axiosInstance);
}

export function GroupsServiceApi() {
  return GroupsApiFactory(Config, `${baseUrl}/authservice/v1`, axiosInstance);
}
