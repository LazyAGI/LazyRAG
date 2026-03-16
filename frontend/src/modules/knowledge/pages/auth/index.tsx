import { Tabs } from "antd";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { KnowledgeBaseServiceApi } from "@/modules/knowledge/utils/request";

import { MemberType } from "@/modules/knowledge/constants/common";
import MemberList from "./components/MemberList";
import { Dataset } from "@/api/generated/knowledge-client";
import { DetailPageHeader } from "@/components/ui";

const Authorize = () => {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [detail, setDetail] = useState<Dataset>();

  const searchParams = new URLSearchParams(location.search);

  useEffect(() => {
    fetchDetail();
  }, []);

  function fetchDetail() {
    KnowledgeBaseServiceApi()
      .datasetServiceGetDataset({ dataset: id })
      .then((res) => {
        setDetail(res.data);
      });
  }

  return (
    <div className="knowledge-container w-full !items-start">
      <DetailPageHeader
        className="mb-4"
        breadcrumbs={[
          { title: "知识库", href: "/appplatform/lib/knowledge/list" },
          { title: detail?.display_name },
        ]}
        title={`${detail?.display_name} 知识库授权`}
        onBack={() => {
          navigate(-1);
        }}
      />
      <Tabs
        defaultActiveKey={`${searchParams.get("tab") || MemberType.USER}`}
        onChange={(v) => {
          searchParams.set("tab", v);
          navigate(`${location.pathname}?${searchParams.toString()}`, {
            replace: true,
          });
        }}
        className="w-full"
      >
        <Tabs.TabPane tab={"用户"} key={`${MemberType.USER}`}>
          {detail && (
            <MemberList memberType={MemberType.USER} detail={detail} />
          )}
        </Tabs.TabPane>
        <Tabs.TabPane tab={"用户组"} key={`${MemberType.GROUP}`}>
          {detail && (
            <MemberList memberType={MemberType.GROUP} detail={detail} />
          )}
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default Authorize;
