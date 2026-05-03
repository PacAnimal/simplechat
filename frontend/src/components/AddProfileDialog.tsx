import { useState } from "react";
import { api } from "../lib/api";
import type { Profile } from "../types";
import { AVATARS } from "../types";
import { cn } from "../lib/utils";

interface Props {
  onCreated: (profile: Profile) => void;
  onClose: () => void;
}

export default function AddProfileDialog({ onCreated, onClose }: Props) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [avatar, setAvatar] = useState(() => Math.floor(Math.random() * AVATARS.length));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const passwordMismatch = confirm.length > 0 && password !== confirm;
  const canSubmit = !saving && name.trim().length > 0 && password.length > 0 && password === confirm;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError("");
    try {
      const profile = await api.createProfile(name.trim(), password, avatar);
      onCreated(profile);
    } catch (err: unknown) {
      if (err instanceof Error && err.message.includes("409")) {
        setError("That name is already taken");
      } else {
        setError("Failed to create profile");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-md p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-primary mb-5">Create profile</h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted uppercase tracking-wide">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              autoFocus
              maxLength={100}
              className="bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
              data-testid="add-profile-name"
            />
          </div>

          {/* password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted uppercase tracking-wide">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Choose a password"
              className="bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
              data-testid="add-profile-password"
            />
          </div>

          {/* confirm password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted uppercase tracking-wide">Confirm password</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat your password"
              className={cn(
                "bg-input border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none transition-colors",
                passwordMismatch ? "border-red-400 focus:border-red-400" : "border-border focus:border-accent/60",
              )}
              data-testid="add-profile-confirm"
            />
            {passwordMismatch && (
              <p className="text-xs text-red-400">Passwords don't match</p>
            )}
          </div>

          {/* avatar picker */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium text-muted uppercase tracking-wide">Avatar</label>
            <div className="grid grid-cols-10 gap-2">
              {AVATARS.map((av, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setAvatar(i)}
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center text-xl transition-all",
                    avatar === i ? "ring-2 ring-accent ring-offset-2 ring-offset-elevated scale-110" : "hover:scale-105 opacity-70 hover:opacity-100",
                  )}
                  style={{ backgroundColor: av.bg }}
                  title={av.emoji}
                >
                  {av.emoji}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="flex-1 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50"
              data-testid="add-profile-submit"
            >
              {saving ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
