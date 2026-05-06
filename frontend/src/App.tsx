import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import NewChatDialog from "./components/NewChatDialog";
import ProfilePicker from "./components/ProfilePicker";
import { clearToken, getStoredProfile } from "./lib/api";
import { StreamProvider } from "./lib/StreamContext";
import type { Chat, Profile } from "./types";

export default function App() {
  const [profile, setProfile] = useState<Profile | null>(() => getStoredProfile());
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | undefined>(undefined);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // listen for 401 events from api.ts
  useEffect(() => {
    function handleUnauthorized() {
      setProfile(null);
      setSelectedChatId(null);
    }
    window.addEventListener("simplechat:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("simplechat:unauthorized", handleUnauthorized);
  }, []);

  function handleLogin(p: Profile) {
    setProfile(p);
    setSelectedChatId(null);
  }

  function handleLogout() {
    clearToken();
    setProfile(null);
    setSelectedChatId(null);
  }

  function handleSelectChat(id: number | null) {
    setSelectedChatId(id);
    setSidebarOpen(false);
  }

  function handleProfileUpdated(p: Profile) {
    setProfile(p);
  }

  if (!profile) {
    return <ProfilePicker onLogin={handleLogin} />;
  }

  function handleNewChat(initialMessage?: string) {
    setPendingMessage(initialMessage);
    setNewChatOpen(true);
  }

  function handleChatCreated(chat: Chat) {
    setSelectedChatId(chat.id);
    setNewChatOpen(false);
    setPendingMessage(undefined);
    setSidebarOpen(false);
  }

  return (
    <StreamProvider>
      <div className="flex h-full bg-canvas text-primary">
        {/* mobile backdrop */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-30 wide:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <Sidebar
          profile={profile}
          selectedChatId={selectedChatId}
          onSelectChat={handleSelectChat}
          onNewChat={() => { handleNewChat(); setSidebarOpen(false); }}
          onLogout={handleLogout}
          onProfileUpdated={handleProfileUpdated}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <main className="flex-1 flex flex-col min-w-0 bg-canvas">
          {selectedChatId ? (
            <ChatWindow
              key={selectedChatId}
              chatId={selectedChatId}
              initialMessage={pendingMessage}
              onOpenSidebar={() => setSidebarOpen(true)}
            />
          ) : (
            <Welcome onNewChat={handleNewChat} onOpenSidebar={() => setSidebarOpen(true)} />
          )}
        </main>

        {newChatOpen && (
          <NewChatDialog
            onCreated={handleChatCreated}
            onClose={() => setNewChatOpen(false)}
          />
        )}
      </div>
    </StreamProvider>
  );
}

const SUGGESTIONS = [
  { icon: "✍️", label: "Write something", prompt: "Write me a short creative story about a time traveler." },
  { icon: "🔍", label: "Search the web", prompt: "What's happening in the world today?" },
  { icon: "🎨", label: "Generate an image", prompt: "Generate an image of a futuristic city at sunset." },
  { icon: "💡", label: "Explain a concept", prompt: "Explain quantum entanglement in simple terms." },
];

function Welcome({ onNewChat, onOpenSidebar }: { onNewChat: (initialMessage?: string) => void; onOpenSidebar: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 px-8 select-none relative">
      <button
        onClick={onOpenSidebar}
        className="absolute top-4 left-4 wide:hidden p-2 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
        aria-label="Open sidebar"
      >
        <Menu size={20} />
      </button>
      <div className="text-center">
        <h1 className="text-4xl font-semibold text-primary mb-3 tracking-tight">SimpleChat</h1>
        <p className="text-secondary text-base">Yet another AI chat web interface.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md">
        {SUGGESTIONS.map(({ icon, label, prompt }) => (
          <SuggestionCard
            key={label}
            icon={icon}
            label={label}
            onClick={() => onNewChat(prompt)}
          />
        ))}
      </div>
      <button
        onClick={() => onNewChat()}
        className="px-7 py-2.5 bg-accent hover:bg-accent-hover text-white font-medium rounded-full transition-colors shadow-lg shadow-accent/20"
        data-testid="welcome-new-chat"
      >
        New chat
      </button>
    </div>
  );
}

function SuggestionCard({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 bg-elevated border border-border rounded-xl px-4 py-3 text-sm text-secondary hover:text-primary hover:border-accent/40 transition-colors text-left"
    >
      <span className="text-lg">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
