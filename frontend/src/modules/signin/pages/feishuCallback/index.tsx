import { message, Spin } from "antd";
import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { finishFeishuLogin } from "@/modules/signin/utils/feishuAuth";


const FeishuCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  useEffect(() => {
    const run = async () => {
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      const error = searchParams.get("error");
      const errorDescription = searchParams.get("error_description");

      if (error) {
        message.error(
          errorDescription || `${t("auth.feishuAuthFailed")}: ${error}`,
        );
        navigate("/login", { replace: true });
        return;
      }

      if (!code || !state) {
        message.error(t("auth.feishuCallbackMissing"));
        navigate("/login", { replace: true });
        return;
      }

      try {
        await finishFeishuLogin(code, state);
        navigate("/agent/chat", { replace: true });
      } catch (err: any) {
        message.error(err?.message || t("auth.feishuLoginUnavailable"));
        navigate("/login", { replace: true });
      }
    };

    void run();
  }, [navigate, searchParams, t]);

  return (
    <div
      className="signin-container"
      style={{
        minHeight: 180,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Spin size="large" tip={t("auth.finishingFeishuLogin")} />
    </div>
  );
};


export default FeishuCallback;
