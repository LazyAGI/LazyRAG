import { Button, Spin, message, Modal, Select, Flex, Input } from "antd";
import { useEffect, useRef, useState } from "react";
import moment from "moment";
import {
  Dataset,
  DatasetAclEnum,
  DatasetMember,
  Role,
} from "@/api/generated/knowledge-client";
import { useNavigate } from "react-router-dom";

import { MemberType } from "@/modules/knowledge/constants/common";
import AddUserModal, { IAddUserModalRef } from "../AddUserModal";
import {
  KnowledgeBaseServiceApi,
  MemberServiceApi,
} from "@/modules/knowledge/utils/request";
import { ListPageTable } from "@/components/ui";
const { Option } = Select;
const { confirm } = Modal;
const { Search } = Input;

interface IProps {
  memberType: MemberType;
  detail: Dataset | undefined;
}

interface Member {
  id: string;
  type: MemberType;
  display_name: string;
}

const MemberList = (props: IProps) => {
  const [searchValue, setSearchValue] = useState("");
  const [dataSource, setDataSource] = useState<(DatasetMember & Member)[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    showSizeChanger: false,
  });
  const [currentDetail, setCurrentDetail] = useState<Dataset>();

  const addUserModalRef = useRef<IAddUserModalRef>();

  const navigate = useNavigate();

  const { memberType, detail } = props;

  const isGroup = memberType === MemberType.GROUP;

  const showDataSource = dataSource.filter((item: DatasetMember & Member) => {
    return (
      !searchValue ||
      item?.display_name?.toLowerCase().includes(searchValue?.toLowerCase())
    );
  });

  const columns = [
    {
      title: isGroup ? "用户组名称" : "用户名称",
      dataIndex: "display_name",
    },
    {
      title: "角色",
      dataIndex: "role",
      width: 156,
      render: (role: Role) => {
        return (
          <Select value={role?.display_name} disabled style={{ width: "100%" }}>
            <Option key={role.role} value={role.display_name}>
              {role.display_name}
            </Option>
          </Select>
        );
      },
    },
    // TODO remove date this version.
    // {
    //   title: '更新日期',
    //   dataIndex: 'create_time',
    //   width: 200,
    //   render: (text: string) => (moment(text).isValid() ? moment(text).format('YYYY-MM-DD HH:mm:ss') : ''),
    // },
    {
      title: "操作",
      key: "action",
      width: 102,
      render: (record: DatasetMember & Member) => {
        return (
          currentDetail?.acl?.includes(DatasetAclEnum.DatasetWrite) && (
            <Button
              type="link"
              danger
              onClick={() => handleDelete(record)}
              style={{ padding: 0, minWidth: "auto" }}
            >
              删除
            </Button>
          )
        );
      },
    },
  ];

  useEffect(() => {
    setCurrentDetail(detail);
    if (!detail?.acl?.includes(DatasetAclEnum.DatasetWrite)) {
      // When a non-creator deletes or downgrades their own permissions, they will no longer be able to access the knowledge base and need to return to the knowledge base list page.
      navigate({
        pathname: "/list",
      });
      return;
    }

    getTableData(detail);
  }, []);

  function onSearch(value: string) {
    const str = value?.trim() || "";
    setSearchValue(str);
    pagination.current = 1;
    setPagination({ ...pagination });
  }

  function getTableData(knowledgeBaseDetail: Dataset) {
    setLoading(true);
    // The interface cannot support distinguishing users and user groups and can only be implemented on the front end.
    MemberServiceApi()
      .datasetMemberServiceListDatasetMembers({
        dataset: knowledgeBaseDetail?.dataset_id || "",
      })
      .then((res) => {
        const list = (res.data.dataset_members || [])
          .map((item: DatasetMember) => {
            const groupUser = !!item.group_id;
            return {
              ...item,
              type: groupUser ? MemberType.GROUP : MemberType.USER,
              id: (groupUser ? item.group_id : item.user_id) || "",
              display_name: (groupUser ? item.group : item.user) || "",
            };
          })
          .filter((item) => item.type === memberType && item.id)
          .sort((a, b) => {
            return (
              moment(b?.create_time).valueOf() -
              moment(a?.create_time).valueOf()
            );
          });
        setDataSource(list);
        pagination.current = 1;
        setPagination({ ...pagination });
      })
      .finally(() => {
        setLoading(false);
      });
  }

  function isCreator(record: DatasetMember & Member) {
    return record.role.role === "dataset_owner";
  }

  function handleDelete(record: DatasetMember & Member) {
    // 检查是否是创建者，如果是则不允许删除
    if (isCreator(record)) {
      message.error("无法删除创建者权限");
      return;
    }

    confirm({
      title: "提示",
      content: `确定删除${isGroup ? "用户组" : "用户"} ${record.display_name} 的知识库 ${record.role.display_name} 相应权限？`,
      centered: true,
      okType: "danger",
      onOk() {
        return new Promise((resolve, reject) => {
          MemberServiceApi()
            .datasetMemberServiceDeleteDatasetMember({
              dataset: record.dataset_id || "",
              member: `type/${isGroup ? "group" : "user"}/id/${record.id}/role/${record.role.role}`,
            })
            .then(() => {
              resolve("");
              message.success(`删除知识库${isGroup ? "用户组" : "用户"}成功`);
              fetchDetail();
            })
            .catch((err) => {
              console.error("Delete knowledge base user/group error: ", err);
              reject(false);
            });
        });
      },
    });
  }

  function handleTableChange(paginationInfo: any) {
    setPagination(paginationInfo);
  }

  function fetchDetail() {
    KnowledgeBaseServiceApi()
      .datasetServiceGetDataset({ dataset: currentDetail?.dataset_id || "" })
      .then((res) => {
        setCurrentDetail(res.data);
        getTableData(res.data);
      })
      .catch((err) => {
        if (err?.response?.data?.code === 10104) {
          // When a non-creator deletes or downgrades their own permissions, they will no longer be able to access the knowledge base and need to return to the knowledge base list page.
          navigate({
            pathname: "/list",
          });
          return;
        }
      });
  }

  return (
    <Spin spinning={loading}>
      <Flex
        style={{
          width: "100%",
          justifyContent: "space-between",
          marginBottom: "16px",
        }}
      >
        <Search
          placeholder={isGroup ? "用户组名称" : "用户名称"}
          onSearch={onSearch}
          style={{ width: 300 }}
          allowClear
        />
        {currentDetail?.acl?.includes(DatasetAclEnum.DatasetWrite) && (
          <Button
            type="primary"
            onClick={() =>
              addUserModalRef.current?.handleOpen({
                dataset_id: currentDetail.dataset_id || "",
                memberType,
              })
            }
          >
            {`添加${isGroup ? "用户组" : "用户"}`}
          </Button>
        )}
      </Flex>
      <ListPageTable
        columns={columns}
        dataSource={showDataSource}
        rowKey="user_id"
        pagination={pagination}
        onChange={handleTableChange}
        className="w-full"
        scroll={{
          y: "calc(100vh - 350px)",
        }}
      />

      <AddUserModal
        ref={addUserModalRef}
        onOk={() => {
          fetchDetail();
        }}
      />
    </Spin>
  );
};

export default MemberList;
