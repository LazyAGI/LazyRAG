import { Outlet } from "react-router-dom";
import ChatLayout from "./layout";
import "./style.css";

export default function ChatApp() {
  return (
    <ChatLayout>
      <Outlet />
    </ChatLayout>
  );
}
