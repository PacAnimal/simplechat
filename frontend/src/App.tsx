import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import NewChatDialog from "./components/NewChatDialog";
import type { Chat } from "./types";

export default function App() {
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [newChatOpen, setNewChatOpen] = useState(false);

  function handleChatCreated(chat: Chat) {
    setSelectedChatId(chat.id);
    setNewChatOpen(false);
  }

  return (
    <div className="flex h-full bg-canvas text-primary">
      <Sidebar
        selectedChatId={selectedChatId}
        onSelectChat={setSelectedChatId}
        onNewChat={() => setNewChatOpen(true)}
      />

      <main className="flex-1 flex flex-col min-w-0 bg-canvas">
        {selectedChatId ? (
          <ChatWindow
            key={selectedChatId}
            chatId={selectedChatId}
            onDeleted={() => setSelectedChatId(null)}
          />
        ) : (
          <Welcome onNewChat={() => setNewChatOpen(true)} />
        )}
      </main>

      {newChatOpen && (
        <NewChatDialog
          onCreated={handleChatCreated}
          onClose={() => setNewChatOpen(false)}
        />
      )}
    </div>
  );
}

function Welcome({ onNewChat }: { onNewChat: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 px-8 select-none">
      <div className="text-center">
        <h1 className="text-4xl font-semibold text-primary mb-3 tracking-tight">SimpleChat</h1>
        <p className="text-secondary text-base">OpenAI and Anthropic in one place.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md">
        <SuggestionCard icon="✍️" label="Write something" />
        <SuggestionCard icon="🔍" label="Search the web" />
        <SuggestionCard icon="🎨" label="Generate an image" />
        <SuggestionCard icon="💡" label="Explain a concept" />
      </div>
      <button
        onClick={onNewChat}
        className="px-7 py-2.5 bg-accent hover:bg-accent-hover text-white font-medium rounded-full transition-colors shadow-lg shadow-accent/20"
        data-testid="welcome-new-chat"
      >
        New chat
      </button>
    </div>
  );
}

function SuggestionCard({ icon, label }: { icon: string; label: string }) {
  return (
    <div className="flex items-center gap-3 bg-elevated border border-border rounded-xl px-4 py-3 text-sm text-secondary hover:text-primary hover:border-accent/40 transition-colors cursor-default">
      <span className="text-lg">{icon}</span>
      <span>{label}</span>
    </div>
  );
}
