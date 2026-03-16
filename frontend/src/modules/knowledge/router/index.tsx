import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";

import List from "@/modules/knowledge/pages/list";
import Auth from "@/modules/knowledge/pages/auth";
import Detail from "@/modules/knowledge/pages/detail";
import Knowledge from "@/modules/knowledge/pages/knowledge";

const router = createBrowserRouter(
  [
    { path: "/", element: <Navigate to="/list" replace /> },
    { path: "/list", element: <List /> },
    { path: "/auth/:id", element: <Auth /> },
    { path: "/detail/:id", element: <Detail /> },
    {
      path: "/knowledge/:knowledgeBaseId/:knowledgeId",
      element: <Knowledge />,
    },
  ],
  {
    basename:
      (typeof window !== "undefined" && window.BASENAME
        ? window.BASENAME
        : "") + "/lib/knowledge",
  },
);

const AppRouter = () => <RouterProvider router={router} />;

export default AppRouter;
