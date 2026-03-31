import { Form, message, Modal, Select } from "antd";
import { debounce } from "lodash";
import { forwardRef, Ref, useImperativeHandle, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  MemberType,
  ROLE_TYPE_INFO,
} from "@/modules/knowledge/constants/common";
import {
  MemberServiceApi,
} from "@/modules/knowledge/utils/request";
import { axiosInstance, BASE_URL } from "@/components/request";
import { createUserApi } from "@/modules/signin/utils/request";

const { Option } = Select;

interface IData {
  dataset_id: string;
  memberType: MemberType;
}

export interface IAddUserModalRef {
  handleOpen: (data: IData) => void;
}

interface IProps {
  onOk: () => void;
}

const AddUserModal = (props: IProps, ref: Ref<unknown> | undefined) => {
  const { t } = useTranslation();
  const [data, setData] = useState<IData>();
  const [visible, setVisible] = useState(false);
  const [userList, setUserList] = useState<
    Array<{ value: string; label: string }>
  >([]);
  const [loading, setLoading] = useState(false);

  const { onOk } = props;

  const [form] = Form.useForm();

  const isGroup = data?.memberType === MemberType.GROUP;

  const debounceGetUser = debounce((v) => getUser(v), 300);

  useImperativeHandle(ref, () => ({
    handleOpen,
  }));

  function handleOpen(info: IData) {
    setData(info);
    setVisible(true);
    getUser("", info.memberType);
  }

  function handleClose() {
    form.resetFields();
    setData(undefined);
    setVisible(false);
    setUserList([]);
    setLoading(false);
  }

  function submit() {
    form.validateFields().then(async (values) => {
      setLoading(true);
      if (values.memberName.length > 0) {
        try {
          await MemberServiceApi().datasetMemberServiceBatchAddDatasetMember({
            dataset: data?.dataset_id || "",
            batchAddDatasetMemberRequest: {
              parent: data?.dataset_id || "",
              role: { role: values.roleName },
              [data?.memberType === MemberType.GROUP
                ? "group_id_list"
                : "user_id_list"]: values.memberName,
            },
          });
        } catch (err) {
          setLoading(false);
          console.error("Add knowledge base member error: ", err);
          return;
        }
      }

      message.success(t("knowledge.addSuccess"));
      setLoading(false);
      handleClose();
      onOk();
    });
  }

  function getUser(query?: string, memberType = data?.memberType) {
    if (memberType === MemberType.GROUP) {
      axiosInstance
        .get(`${BASE_URL}/api/authservice/group`, {
          params: {
            page: 1,
            page_size: 200,
            search: query || undefined,
          },
        })
        .then((res) => {
          const resData = res.data as any;
          const list = ((resData.data?.groups || resData.groups) || []).map(
            (item: { group_id: string; group_name: string }) => {
              return { value: item.group_id, label: item.group_name };
            },
          );
          setUserList(list);
        });
    } else {
      createUserApi()
        .listUsersApiAuthserviceUserGet({
          page: 1,
          pageSize: 20,
          search: query || undefined,
        })
        .then((res) => {
          const resData = res.data as any;
          const responseData = resData.data || resData;
          const list = (responseData.users || []).map(
            (item: {
              user_id: string;
              display_name?: string;
              username?: string;
            }) => {
              return {
                value: item.user_id,
                label: item.display_name || item.username || item.user_id,
              };
            },
          );
          setUserList(list);
        });
    }
  }

  return (
    <Modal
      open={visible}
      width={500}
      title={isGroup ? t("knowledge.addGroup") : t("knowledge.addUser")}
      okText={t("common.save")}
      onCancel={handleClose}
      onOk={submit}
      centered
      okButtonProps={{ disabled: loading }}
      maskClosable={false}
    >
      <Form
        form={form}
        layout="vertical"
        colon={false}
        initialValues={{ roleName: "dataset_user" }}
      >
        <Form.Item
          label={isGroup ? t("knowledge.groupName") : t("knowledge.userName")}
          name="memberName"
          rules={[
            {
              required: true,
              message: isGroup
                ? t("knowledge.selectGroupName")
                : t("knowledge.selectUserName"),
            },
            {
              max: 20,
              type: "array",
              message: isGroup
                ? t("knowledge.maxAddGroups")
                : t("knowledge.maxAddUsers"),
            },
          ]}
        >
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={isGroup ? t("knowledge.groupName") : t("knowledge.userName")}
            popupMatchSelectWidth
            virtual={true}
            showSearch
            optionLabelProp="tag"
            style={{ flex: 1 }}
            onSearch={debounceGetUser}
            filterOption={false}
            options={userList.map((item) => ({
              value: item.value,
              label: (
                <div style={{ display: "flex" }}>
                  {item.label}
                  <span style={{ margin: "0 4px", flex: 1 }}></span>
                  {item.value}
                </div>
              ),
              tag: item.label,
            }))}
            onDropdownVisibleChange={(visible) => {
              if (!visible) {
                debounceGetUser("");
              }
            }}
          />
        </Form.Item>
        <Form.Item
          label={t("knowledge.role")}
          name="roleName"
          rules={[{ required: true, message: t("knowledge.selectRole") }]}
        >
          <Select placeholder={t("knowledge.selectPlease")}>
            {/* This version only can select user. */}
            {ROLE_TYPE_INFO.map((item) => {
              return (
                <Option key={item.id} value={item.id}>
                  {item.title}
                </Option>
              );
            })}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default forwardRef(AddUserModal);
