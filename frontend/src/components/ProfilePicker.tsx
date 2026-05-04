import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PlusIcon, LockIcon, BotIcon } from "lucide-react";
import { api, setToken, storeProfile } from "../lib/api";
import type { Profile } from "../types";
import { AVATARS } from "../types";
import AddProfileDialog from "./AddProfileDialog";

interface Props {
  onLogin: (profile: Profile) => void;
}

export default function ProfilePicker({ onLogin }: Props) {
  const [addOpen, setAddOpen] = useState(false);
  const [loginTarget, setLoginTarget] = useState<Profile | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [logging, setLogging] = useState(false);

  const { data: profiles = [], refetch } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.listProfiles,
  });

  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
  });

  const canCreate = config?.can_create_profile ?? false;

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!loginTarget) return;
    setLogging(true);
    setError("");
    try {
      const res = await api.loginProfile(loginTarget.id, password);
      setToken(res.token);
      storeProfile(res.profile);
      onLogin(res.profile);
    } catch (err: unknown) {
      setError(err instanceof Error && err.message === "UNAUTHORIZED" ? "Wrong password" : "Login failed");
    } finally {
      setLogging(false);
    }
  }

  function openLogin(profile: Profile) {
    setLoginTarget(profile);
    setPassword("");
    setError("");
  }

  function closeLogin() {
    setLoginTarget(null);
    setPassword("");
    setError("");
  }

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* header */}
        <div className="flex flex-col items-center gap-3 mb-10">
          <div className="w-12 h-12 rounded-2xl bg-accent/20 flex items-center justify-center">
            <BotIcon size={24} className="text-accent" />
          </div>
          <h1 className="text-3xl font-semibold text-primary tracking-tight">SimpleChat</h1>
          <p className="text-secondary text-sm">Choose a profile to continue</p>
        </div>

        {/* profile grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
          {profiles.map((profile) => (
            <ProfileCard key={profile.id} profile={profile} onClick={() => openLogin(profile)} />
          ))}

          {/* add profile button — only shown when creation is permitted */}
          {canCreate && (
            <button
              onClick={() => setAddOpen(true)}
              className="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border hover:border-accent/50 bg-elevated hover:bg-hover transition-colors p-6 min-h-[120px]"
              data-testid="add-profile-button"
            >
              <div className="w-10 h-10 rounded-full bg-hover flex items-center justify-center">
                <PlusIcon size={20} className="text-muted" />
              </div>
              <span className="text-xs text-muted font-medium">Add profile</span>
            </button>
          )}
        </div>
      </div>

      {/* login modal */}
      {loginTarget && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
            <div className="flex flex-col items-center gap-3 mb-6">
              <Avatar profile={loginTarget} size="lg" />
              <h2 className="text-lg font-semibold text-primary">{loginTarget.name}</h2>
            </div>
            <form onSubmit={handleLogin} className="flex flex-col gap-3">
              <div className="relative">
                <LockIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  autoFocus
                  className="w-full bg-input border border-border rounded-xl pl-9 pr-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
                  data-testid="profile-password-input"
                />
              </div>
              {error && <p className="text-xs text-red-400 text-center">{error}</p>}
              <div className="flex gap-2 mt-1">
                <button
                  type="button"
                  onClick={closeLogin}
                  className="flex-1 py-2.5 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={logging || !password}
                  className="flex-1 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50"
                  data-testid="profile-login-button"
                >
                  {logging ? "…" : "Sign in"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {addOpen && (
        <AddProfileDialog
          onCreated={(profile) => {
            refetch();
            setAddOpen(false);
            openLogin(profile);
          }}
          onClose={() => setAddOpen(false)}
        />
      )}
    </div>
  );
}

function ProfileCard({ profile, onClick }: { profile: Profile; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-2.5 rounded-2xl bg-elevated border border-border hover:border-accent/40 hover:bg-hover transition-colors p-5 min-h-[120px] justify-center group"
      data-testid={`profile-card-${profile.id}`}
    >
      <Avatar profile={profile} size="md" />
      <span className="text-sm font-medium text-primary truncate w-full text-center">{profile.name}</span>
    </button>
  );
}

export function Avatar({ profile, size = "md", colorOverride }: { profile: Profile; size?: "sm" | "md" | "lg"; colorOverride?: string }) {
  const av = AVATARS[profile.avatar % AVATARS.length];
  const bg = colorOverride ?? profile.avatar_color ?? av.bg;
  const sizeClass = size === "lg" ? "w-20 h-20 text-[3.5rem]" : size === "sm" ? "w-7 h-7 text-xl" : "w-16 h-16 text-[3rem]";
  return (
    <div
      className={`${sizeClass} rounded-full flex items-center justify-center select-none flex-shrink-0`}
      style={{ backgroundColor: bg }}
    >
      {av.emoji}
    </div>
  );
}
