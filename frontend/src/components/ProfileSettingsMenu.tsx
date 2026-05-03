import { useEffect, useRef, useState } from "react";
import { Settings2Icon, LogOutIcon, UserCircleIcon, KeyRoundIcon } from "lucide-react";
import { api, storeProfile } from "../lib/api";
import type { Profile } from "../types";
import { AVATARS } from "../types";
import { Avatar } from "./ProfilePicker";
import { cn } from "../lib/utils";

interface Props {
  profile: Profile;
  onProfileUpdated: (profile: Profile) => void;
  onLogout: () => void;
}

export default function ProfileSettingsMenu({ profile, onProfileUpdated, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"avatar" | "password" | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setPanel(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleOpenPanel(p: "avatar" | "password") {
    setPanel(p);
    setOpen(false);
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => { setOpen((v) => !v); setPanel(null); }}
        className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
        title="Profile settings"
        data-testid="profile-settings-button"
      >
        <Settings2Icon size={16} />
      </button>

      {open && (
        <div className="absolute bottom-full right-0 mb-2 w-48 bg-elevated border border-border rounded-xl shadow-lg overflow-hidden z-50">
          <MenuItem icon={<UserCircleIcon size={14} />} label="Change avatar" onClick={() => handleOpenPanel("avatar")} />
          <MenuItem icon={<KeyRoundIcon size={14} />} label="Change password" onClick={() => handleOpenPanel("password")} />
          <div className="mx-2 border-t border-border my-1" />
          <MenuItem icon={<LogOutIcon size={14} />} label="Log out" onClick={onLogout} danger />
        </div>
      )}

      {panel === "avatar" && (
        <AvatarPanel
          profile={profile}
          onUpdated={(p) => { onProfileUpdated(p); setPanel(null); }}
          onClose={() => setPanel(null)}
        />
      )}

      {panel === "password" && (
        <PasswordPanel
          profile={profile}
          onDone={() => setPanel(null)}
        />
      )}
    </div>
  );
}

function MenuItem({ icon, label, onClick, danger = false }: { icon: React.ReactNode; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors text-left",
        danger ? "text-red-400 hover:bg-red-500/10" : "text-secondary hover:bg-hover hover:text-primary",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function AvatarPanel({ profile, onUpdated, onClose }: { profile: Profile; onUpdated: (p: Profile) => void; onClose: () => void }) {
  const [selected, setSelected] = useState(profile.avatar);
  const [saving, setSaving] = useState(false);

  const [error, setError] = useState("");

  async function handleSave() {
    if (selected === profile.avatar) { onClose(); return; }
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateAvatar(profile.id, selected);
      storeProfile(updated);
      onUpdated(updated);
    } catch {
      setError("Failed to save avatar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
        <h2 className="text-base font-semibold text-primary mb-4">Change avatar</h2>
        <div className="flex justify-center mb-4">
          <Avatar profile={{ ...profile, avatar: selected }} size="lg" />
        </div>
        <div className="grid grid-cols-10 gap-1.5 mb-5">
          {AVATARS.map((av, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setSelected(i)}
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center text-base transition-all",
                selected === i ? "ring-2 ring-accent ring-offset-2 ring-offset-elevated scale-110" : "opacity-60 hover:opacity-100 hover:scale-105",
              )}
              style={{ backgroundColor: av.bg }}
            >
              {av.emoji}
            </button>
          ))}
        </div>
        {error && <p className="text-xs text-red-400 mb-1">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} className="flex-1 py-2 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50">
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PasswordPanel({ profile, onDone }: { profile: Profile; onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!current || !next) return;
    setSaving(true);
    setError("");
    try {
      await api.changePassword(profile.id, current, next);
      onDone();
    } catch (err: unknown) {
      if (err instanceof Error && err.message.startsWith("400:")) {
        setError("Current password is wrong");
      } else {
        setError("Failed to change password");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
        <h2 className="text-base font-semibold text-primary mb-4">Change password</h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="Current password"
            autoFocus
            className="bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
          />
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="New password"
            className="bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onDone} className="flex-1 py-2.5 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving || !current || !next} className="flex-1 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
