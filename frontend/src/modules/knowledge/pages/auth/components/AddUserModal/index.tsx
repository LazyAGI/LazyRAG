import { Form, message, Modal, Select } from "antd";
import { debounce } from "lodash";
import { forwardRef, Ref, useImperativeHandle, useState } from "react";

import {
  MemberType,
  ROLE_TYPE_INFO,
} from "@/modules/knowledge/constants/common";
import {
  UsersServiceApi,
  GroupsServiceApi,
  MemberServiceApi,
} from "@/modules/knowledge/utils/request";

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

      message.success("添加成功");
      setLoading(false);
      handleClose();
      onOk();
    });
  }

  function getUser(query?: string, memberType = data?.memberType) {
    if (memberType === MemberType.GROUP) {
      GroupsServiceApi()
        .listUserGroups({ groupName: query, perPage: 99999 })
        .then((res) => {
          const list = (res.data.data.groups || []).map(
            (item: { id: string; group_name: string }) => {
              return { value: item.id, label: item.group_name };
            },
          );
          setUserList(list);
        });
    } else {
      UsersServiceApi()
        .listUsers({ userName: query, perPage: 99999 })
        .then((res) => {
          const list = (res.data.data.users || []).map(
            (item: { id: string; display_name: string }) => {
              return { value: item.id, label: item.display_name };
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
      title={isGroup ? "添加用户组" : "添加用户"}
      okText={"保存"}
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
          label={isGroup ? "用户组名称" : "用户名称"}
          name="memberName"
          rules={[
            {
              required: true,
              message: isGroup ? "请选择用户组名称" : "请选择用户名称",
            },
            {
              max: 20,
              type: "array",
              message: isGroup
                ? "最多同时添加 20 个用户组"
                : "最多同时添加 20 个用户",
            },
          ]}
        >
          <Select
            mode="multiple"
            tokenSeparators={[" "]}
            allowClear
            placeholder={isGroup ? "用户组名称" : "用户名称"}
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
          label={"角色"}
          name="roleName"
          rules={[{ required: true, message: "请选择角色" }]}
        >
          <Select placeholder={"请选择"}>
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
