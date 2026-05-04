import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, Trash2Icon, MessageSquareIcon, BotIcon, SearchIcon, XIcon } from "lucide-react";
import { api } from "../lib/api";
import type { Chat, MessageSearchResult, Profile } from "../types";
import { PROVIDER_LABELS } from "../types";
import { cn } from "../lib/utils";
import { Avatar } from "./ProfilePicker";
import ProfileSettingsMenu from "./ProfileSettingsMenu";

interface Props {
  profile: Profile;
  selectedChatId: number | null;
  onSelectChat: (id: number | null) => void;
  onNewChat: () => void;
  onLogout: () => void;
  onProfileUpdated: (profile: Profile) => void;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function Sidebar({ profile, selectedChatId, onSelectChat, onNewChat, onLogout, onProfileUpdated }: Props) {
  const qc = useQueryClient();
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounce(searchQuery, 300);

  const { data: chats = [] } = useQuery({
    queryKey: ["chats"],
    queryFn: api.listChats,
    refetchInterval: 15_000,
  });

  const { data: searchResults = [], isFetching: searching } = useQuery({
    queryKey: ["search", debouncedQuery],
    queryFn: () => api.searchMessages(debouncedQuery),
    enabled: debouncedQuery.trim().length > 0,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (searchOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 50);
    } else {
      setSearchQuery("");
    }
  }, [searchOpen]);

  const deleteMutation = useMutation({
    mutationFn: api.deleteChat,
    onSuccess: (_data, id) => {
      setConfirmDeleteId(null);
      if (id === selectedChatId) onSelectChat(null);
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  function handleDeleteClick(e: React.MouseEvent, chat: Chat) {
    e.stopPropagation();
    setConfirmDeleteId(chat.id);
  }

  function handleConfirmDelete(e: React.MouseEvent, id: number) {
    e.stopPropagation();
    deleteMutation.mutate(id);
  }

  function handleCancelDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setConfirmDeleteId(null);
  }

  function handleSearchResultClick(result: MessageSearchResult) {
    onSelectChat(result.chat_id);
    setSearchOpen(false);
  }

  return (
    <aside
      className="w-64 flex-shrink-0 flex flex-col bg-sidebar h-full"
      data-testid="sidebar"
    >
      {/* logo + action buttons */}
      <div className="flex items-center justify-between px-3 pt-4 pb-2">
        <div className="flex items-center gap-2 px-2">
          <BotIcon size={20} className="text-accent" />
          <span className="text-sm font-semibold text-primary tracking-tight">SimpleChat</span>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setSearchOpen((o) => !o)}
            className={cn(
              "p-1.5 rounded-lg transition-colors",
              searchOpen
                ? "bg-accent/15 text-accent"
                : "hover:bg-hover text-muted hover:text-primary",
            )}
            title="Search messages"
            data-testid="search-button"
          >
            <SearchIcon size={16} />
          </button>
          <button
            onClick={onNewChat}
            className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
            title="New chat"
            data-testid="new-chat-button"
          >
            <PlusIcon size={18} />
          </button>
        </div>
      </div>

      {/* search panel */}
      {searchOpen && (
        <div className="px-3 pb-2">
          <div className="flex items-center gap-2 bg-input border border-border rounded-lg px-2.5 py-1.5 focus-within:border-accent/60 transition-colors">
            <SearchIcon size={13} className="text-muted flex-shrink-0" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search messages…"
              className="flex-1 bg-transparent text-xs text-primary placeholder-muted outline-none"
              data-testid="search-input"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="text-muted hover:text-primary">
                <XIcon size={11} />
              </button>
            )}
          </div>
          {debouncedQuery.trim() && (
            <div className="mt-1 max-h-64 overflow-y-auto">
              {searching ? (
                <p className="text-xs text-muted px-2 py-2">Searching…</p>
              ) : searchResults.length === 0 ? (
                <p className="text-xs text-muted px-2 py-2">No results</p>
              ) : (
                searchResults.map((r) => (
                  <button
                    key={r.message_id}
                    onClick={() => handleSearchResultClick(r)}
                    className="w-full text-left px-2 py-2 rounded-lg hover:bg-hover transition-colors"
                  >
                    <p className="text-[0.7rem] font-medium text-accent truncate">{r.chat_title}</p>
                    <p className="text-[0.75rem] text-secondary truncate mt-0.5">
                      <span className="text-muted">{r.role === "user" ? "You: " : "AI: "}</span>
                      {r.content.slice(0, 80)}
                    </p>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* divider */}
      <div className="mx-3 border-t border-border mb-2" />

      {/* chat list */}
      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {chats.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
            <MessageSquareIcon size={24} className="text-muted opacity-50" />
            <p className="text-muted text-xs">No chats yet</p>
          </div>
        ) : (
          <>
            <p className="px-2 py-1 text-[0.7rem] font-semibold uppercase tracking-wider text-muted">Recent</p>
            {chats.map((chat) => (
              <button
                key={chat.id}
                onClick={() => onSelectChat(chat.id)}
                onMouseEnter={() => setHoveredId(chat.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors group my-0.5",
                  selectedChatId === chat.id
                    ? "bg-hover text-primary"
                    : "text-secondary hover:bg-hover hover:text-primary",
                )}
                data-testid={`chat-item-${chat.id}`}
              >
                <MessageSquareIcon size={14} className="flex-shrink-0 opacity-50" />
                <div className="flex-1 min-w-0">
                  <p className="text-[0.8125rem] truncate leading-snug font-medium">
                    {chat.title}
                  </p>
                  <p className="text-[0.7rem] text-muted truncate mt-0.5">
                    {PROVIDER_LABELS[chat.provider]} · {shortModel(chat.model)}
                  </p>
                </div>

                {confirmDeleteId === chat.id ? (
                  <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                    <span className="text-[0.65rem] text-muted">Delete?</span>
                    <button
                      onClick={(e) => handleConfirmDelete(e, chat.id)}
                      className="text-[0.65rem] text-red-400 hover:text-red-300 font-medium px-1"
                      data-testid={`confirm-delete-${chat.id}`}
                    >
                      Yes
                    </button>
                    <button
                      onClick={handleCancelDelete}
                      className="text-[0.65rem] text-muted hover:text-primary font-medium px-1"
                    >
                      No
                    </button>
                  </div>
                ) : (
                  (hoveredId === chat.id || selectedChatId === chat.id) && (
                    <button
                      onClick={(e) => handleDeleteClick(e, chat)}
                      className="flex-shrink-0 p-1 rounded hover:text-red-400 text-muted transition-colors opacity-60 hover:opacity-100"
                      title="Delete"
                      data-testid={`delete-chat-${chat.id}`}
                    >
                      <Trash2Icon size={13} />
                    </button>
                  )
                )}
              </button>
            ))}
          </>
        )}
      </nav>

      {/* profile footer */}
      <div className="mx-3 border-t border-border" />
      <div className="flex items-center gap-2.5 px-3 py-3">
        <Avatar profile={profile} size="sm" />
        <span className="flex-1 text-sm font-medium text-primary truncate">{profile.name}</span>
        <ProfileSettingsMenu
          profile={profile}
          onProfileUpdated={onProfileUpdated}
          onLogout={onLogout}
        />
      </div>
    </aside>
  );
}

function shortModel(model: string): string {
  if (model.startsWith("claude-opus")) return "Opus";
  if (model.startsWith("claude-sonnet")) return "Sonnet";
  if (model.startsWith("claude-haiku")) return "Haiku";
  if (model === "gpt-4o") return "GPT-4o";
  if (model === "gpt-4o-mini") return "4o mini";
  if (model === "gpt-4-turbo") return "GPT-4T";
  if (model === "o1-mini") return "o1-mini";
  return model.slice(0, 10);
}
