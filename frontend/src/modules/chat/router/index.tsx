import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";

// import Chat from '@/pages/chat';
import Home from "@/modules/chat/pages/home";

const router = createBrowserRouter(
  [
    { path: "/", element: <Navigate to="/home" replace /> },
    // { path: '/home', element: <Chat /> },
    { path: "/home", element: <Home /> },
  ],
  { basename: "/#/agent/chat" },
);

const AppRouter = () => <RouterProvider router={router} />;

export default AppRouter;
