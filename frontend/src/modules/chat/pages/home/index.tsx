import NewChatPage from "../newChat";
import "./index.scss";

function Home() {
  return (
    <div className="chat-wrapper">
      <div className="chat-content">
        <NewChatPage />
      </div>
    </div>
  );
}

export default Home;
