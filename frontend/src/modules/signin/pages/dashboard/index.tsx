import { useEffect, useState, createContext } from "react";
import { Outlet } from "react-router-dom";
import { Form, Spin } from "antd";
import bgImage from "@/public/layout-bg-IsmwJvyW.png";
import logoImage from "@/public/Lazy.png";
import "./index.scss";

export const FormContext = createContext<any>(null);

const AppLayout = () => {
  const [form] = Form.useForm();
  const [showLoginUi, setShowLoginUi] = useState(false);

  useEffect(() => {
    setShowLoginUi(true);
  }, []);

  return (
    <FormContext.Provider value={form}>
      <div
        className="dashboard-page"
        style={{
          backgroundImage: `url(${bgImage})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="layout-container">
          <div className="layout-right">
            <div className="layout-content">
              <div>
                <div className="logo-box">
                  <img
                    src={logoImage}
                    alt="logo"
                    style={{ width: 50, height: "auto", marginBottom: 4 }}
                  />
                </div>
              </div>
              <div className="outlet-box">
                {showLoginUi ? (
                  <Outlet />
                ) : (
                  <div
                    style={{
                      minHeight: 120,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                    }}
                  >
                    <Spin size="small" />
                    <span>登录校验中...</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="copy-right mt-10 text-center">
          <p>LazyRAG</p>
        </div>
      </div>
    </FormContext.Provider>
  );
};

export default AppLayout;
