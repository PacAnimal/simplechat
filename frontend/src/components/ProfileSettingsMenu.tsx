import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings2Icon, LogOutIcon, UserCircleIcon, KeyRoundIcon, PencilIcon, UsersIcon, ShieldIcon } from "lucide-react";
import { api, setToken, storeProfile } from "../lib/api";
import type { Profile, ProviderAccess, UserProviderAccess } from "../types";
import { AVATARS } from "../types";
import { Avatar } from "./ProfilePicker";
import { cn } from "../lib/utils";
import { validatePassword } from "../lib/validation";

interface Props {
  profile: Profile;
  onProfileUpdated: (profile: Profile) => void;
  onLogout: () => void;
  onImpersonate: (profile: Profile) => void;
}

// 4 rows × 9 cols — warm → cool → neutral, three brightness steps each
const COLOR_SWATCHES = [
  "#7f1d1d", "#991b1b", "#b91c1c",
  "#7c2d12", "#9a3412", "#c2410c",
  "#78350f", "#92400e", "#b45309",
  "#365314", "#3f6212", "#4d7c0f",
  "#14532d", "#166534", "#15803d",
  "#134e4a", "#115e59", "#0f766e",
  "#0c4a6e", "#075985", "#0369a1",
  "#1e3a8a", "#1e40af", "#1d4ed8",
  "#312e81", "#3730a3", "#4338ca",
  "#4c1d95", "#5b21b6", "#6d28d9",
  "#581c87", "#6b21a8", "#7e22ce",
  "#701a75", "#86198f", "#a21caf",
  "#831843", "#9d174d", "#be185d",
  "#881337", "#9f1239", "#be123c",
  "#1c1917", "#292524", "#44403c",
  "#111827", "#1f2937", "#374151",
  "#0f172a", "#1e293b", "#334155",
  "#18181b", "#27272a", "#3f3f46",
];

export default function ProfileSettingsMenu({ profile, onProfileUpdated, onLogout, onImpersonate }: Props) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"avatar" | "password" | "name" | "impersonate" | "provider-access" | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const minLen = config?.password_min_length ?? 8;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panel !== null) return; // panels manage their own close buttons
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [panel]);

  function handleOpenPanel(p: "avatar" | "password" | "name" | "impersonate" | "provider-access") {
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
          <MenuItem icon={<PencilIcon size={14} />} label="Change name" onClick={() => handleOpenPanel("name")} />
          <MenuItem icon={<KeyRoundIcon size={14} />} label="Change password" onClick={() => handleOpenPanel("password")} />
          {config?.admin && profile.name.toLowerCase() === config.admin && (
            <>
              <div className="mx-2 border-t border-border my-1" />
              <MenuItem icon={<UsersIcon size={14} />} label="Impersonate…" onClick={() => handleOpenPanel("impersonate")} />
              <MenuItem icon={<ShieldIcon size={14} />} label="Provider access…" onClick={() => handleOpenPanel("provider-access")} testId="provider-access-button" />
            </>
          )}
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

      {panel === "name" && (
        <NamePanel
          profile={profile}
          onUpdated={(p) => { onProfileUpdated(p); setPanel(null); }}
          onClose={() => setPanel(null)}
        />
      )}

      {panel === "password" && (
        <PasswordPanel
          profile={profile}
          onDone={() => setPanel(null)}
          minPasswordLength={minLen}
        />
      )}

      {panel === "impersonate" && (
        <ImpersonatePanel
          currentProfile={profile}
          onImpersonate={(p) => { onImpersonate(p); setPanel(null); }}
          onClose={() => setPanel(null)}
        />
      )}

      {panel === "provider-access" && (
        <ProviderAccessPanel onClose={() => setPanel(null)} />
      )}
    </div>
  );
}

function MenuItem({ icon, label, onClick, danger = false, testId }: { icon: React.ReactNode; label: string; onClick: () => void; danger?: boolean; testId?: string }) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
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
  const [color, setColor] = useState<string | null>(profile.avatar_color);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // effective preview color: custom > default from AVATARS
  const previewColor = color ?? AVATARS[selected % AVATARS.length].bg;

  async function handleSave() {
    if (selected === profile.avatar && color === profile.avatar_color) { onClose(); return; }
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateAvatar(profile.id, selected, color);
      storeProfile(updated);
      onUpdated(updated);
    } catch {
      setError("Failed to save avatar");
    } finally {
      setSaving(false);
    }
  }

  function handleEmojiSelect(i: number) {
    setSelected(i);
    // reset color override so new emoji uses its own default
    setColor(null);
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
        <h2 className="text-base font-semibold text-primary mb-4">Change avatar</h2>
        <div className="flex justify-center mb-4">
          <Avatar profile={{ ...profile, avatar: selected, avatar_color: color }} size="lg" />
        </div>

        {/* emoji grid */}
        <div className="grid grid-cols-10 gap-1.5 mb-4">
          {AVATARS.map((av, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleEmojiSelect(i)}
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

        {/* color picker */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-muted">Background color</p>
            {color !== null && (
              <button type="button" onClick={() => setColor(null)} className="text-xs text-muted hover:text-primary transition-colors">
                reset
              </button>
            )}
          </div>
          <div className="grid gap-1.5" style={{ gridTemplateColumns: "repeat(9, 1fr)" }}>
            {COLOR_SWATCHES.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setColor(c)}
                className={cn(
                  "w-full aspect-square rounded-full transition-all",
                  previewColor === c ? "ring-2 ring-accent ring-offset-2 ring-offset-elevated scale-110" : "opacity-70 hover:opacity-100 hover:scale-105",
                )}
                style={{ backgroundColor: c }}
                title={c}
              />
            ))}
          </div>
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

function NamePanel({ profile, onUpdated, onClose }: { profile: Profile; onUpdated: (p: Profile) => void; onClose: () => void }) {
  const [name, setName] = useState(profile.name);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { setError("Name cannot be blank"); return; }
    if (trimmed === profile.name) { onClose(); return; }
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateProfileName(profile.id, trimmed);
      storeProfile(updated);
      onUpdated(updated);
    } catch (err: unknown) {
      if (err instanceof Error && err.message.startsWith("409:")) {
        setError("That name is already taken");
      } else {
        setError("Failed to update name");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
        <h2 className="text-base font-semibold text-primary mb-4">Change name</h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            autoFocus
            className="bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-accent/60 transition-colors"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2.5 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving || !name.trim()} className="flex-1 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const PROVIDERS: { key: keyof ProviderAccess; label: string }[] = [
  { key: "openai", label: "OpenAI" },
  { key: "anthropic", label: "Anthropic" },
  { key: "ollama", label: "Ollama" },
];

function ProviderToggle({ enabled, onChange, testId }: { enabled: boolean; onChange: () => void; testId?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={onChange}
      data-testid={testId}
      className={cn(
        "relative h-6 w-10 flex-shrink-0 rounded-full transition-colors duration-200",
        enabled ? "bg-accent" : "bg-muted/40",
      )}
    >
      <span className={cn(
        "absolute top-1 left-1 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200",
        enabled ? "translate-x-4" : "translate-x-0",
      )} />
    </button>
  );
}

function ProviderAccessPanel({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-provider-access"],
    queryFn: api.getProviderAccess,
  });

  // local optimistic state; null value = user has been reset to defaults
  const [localDefaults, setLocalDefaults] = useState<ProviderAccess | null>(null);
  const [localUsers, setLocalUsers] = useState<Map<number, ProviderAccess | null>>(new Map());

  useEffect(() => {
    if (data && !localDefaults) setLocalDefaults(data.defaults);
  }, [data, localDefaults]);

  const defaults = localDefaults ?? data?.defaults;

  function isOnDefault(u: UserProviderAccess): boolean {
    if (localUsers.has(u.id)) return localUsers.get(u.id) === null;
    return u.provider_access === null;
  }

  function effectiveForUser(u: UserProviderAccess): ProviderAccess {
    const local = localUsers.get(u.id);
    if (local === null) return defaults ?? u.effective_access;
    return local ?? u.effective_access;
  }

  async function toggleDefault(key: keyof ProviderAccess) {
    if (!defaults) return;
    const next = { ...defaults, [key]: !defaults[key] };
    setLocalDefaults(next);
    try {
      await api.updateProviderDefaults(next);
      queryClient.invalidateQueries({ queryKey: ["admin-provider-access"] });
    } catch {
      setLocalDefaults(defaults);
    }
  }

  async function toggleUser(u: UserProviderAccess, key: keyof ProviderAccess) {
    if (!defaults) return;
    const current = effectiveForUser(u);
    const next = { ...current, [key]: !current[key] };
    setLocalUsers((m) => new Map(m).set(u.id, next));
    try {
      await api.updateUserProviderAccess(u.id, next);
      queryClient.invalidateQueries({ queryKey: ["admin-provider-access"] });
    } catch {
      setLocalUsers((m) => { const mm = new Map(m); mm.delete(u.id); return mm; });
    }
  }

  async function resetUser(u: UserProviderAccess) {
    setLocalUsers((m) => new Map(m).set(u.id, null));
    try {
      await api.resetUserProviderAccess(u.id);
      queryClient.invalidateQueries({ queryKey: ["admin-provider-access"] });
    } catch {
      setLocalUsers((m) => { const mm = new Map(m); mm.delete(u.id); return mm; });
    }
  }

  const users = data?.users ?? [];

  return createPortal(
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999] p-6">
      <div data-testid="provider-access-panel" className="bg-elevated border border-border rounded-2xl w-full max-w-3xl p-6 shadow-xl flex flex-col max-h-[85vh]">
        <h2 className="text-base font-semibold text-primary mb-1">Provider access</h2>
        <p className="text-xs text-muted mb-4">Control which AI providers each user can access</p>

        {isLoading && <p className="text-sm text-muted text-center py-6">Loading…</p>}

        {!isLoading && (
          <div className="overflow-auto flex-1 -mx-1 px-1">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left text-xs text-muted font-medium pb-2 pr-4">User</th>
                  {PROVIDERS.map((p) => (
                    <th key={p.key} className="text-center text-xs text-muted font-medium pb-2 px-3 w-24">{p.label}</th>
                  ))}
                  <th className="w-14" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {/* default row */}
                {defaults && (
                  <tr>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-accent/15 text-accent">default</span>
                        <span className="text-xs text-muted">New users inherit these</span>
                      </div>
                    </td>
                    {PROVIDERS.map((p) => (
                      <td key={p.key} className="py-2.5 px-3 text-center">
                        <div className="flex justify-center">
                          <ProviderToggle enabled={defaults[p.key]} onChange={() => toggleDefault(p.key)} testId={`toggle-default-${p.key}`} />
                        </div>
                      </td>
                    ))}
                    <td />
                  </tr>
                )}
                {/* per-user rows */}
                {users.map((u) => {
                  const effective = effectiveForUser(u);
                  const onDefault = isOnDefault(u);
                  return (
                    <tr key={u.id}>
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2">
                          <Avatar profile={u as unknown as Profile} size="sm" />
                          <span className="text-primary">{u.name}</span>
                          {onDefault && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted/20 text-muted">default</span>
                          )}
                        </div>
                      </td>
                      {PROVIDERS.map((p) => (
                        <td key={p.key} className="py-2.5 px-3 text-center">
                          <div className="flex justify-center">
                            <ProviderToggle enabled={effective[p.key]} onChange={() => toggleUser(u, p.key)} testId={`toggle-user-${u.id}-${p.key}`} />
                          </div>
                        </td>
                      ))}
                      <td className="py-2.5 pl-2 text-right">
                        {!onDefault && (
                          <button
                            type="button"
                            onClick={() => resetUser(u)}
                            className="text-[11px] text-muted hover:text-primary transition-colors"
                          >
                            reset
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 pt-3 border-t border-border flex justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ImpersonatePanel({ currentProfile, onImpersonate, onClose }: { currentProfile: Profile; onImpersonate: (p: Profile) => void; onClose: () => void }) {
  const [error, setError] = useState("");
  const { data: profiles, isLoading } = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });
  const others = profiles?.filter((p) => p.id !== currentProfile.id) ?? [];

  async function handleSelect(targetId: number) {
    setError("");
    try {
      const { token, profile } = await api.impersonateProfile(targetId);
      setToken(token);
      storeProfile(profile);
      onImpersonate(profile);
    } catch {
      setError("Failed to impersonate profile");
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-elevated border border-border rounded-2xl w-full max-w-sm p-6 shadow-xl">
        <h2 className="text-base font-semibold text-primary mb-1">Impersonate</h2>
        <p className="text-xs text-muted mb-4">Switch to another user's account</p>
        {isLoading && <p className="text-sm text-muted text-center py-4">Loading…</p>}
        {!isLoading && others.length === 0 && (
          <p className="text-sm text-muted text-center py-4">No other profiles</p>
        )}
        <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
          {others.map((p) => (
            <button
              key={p.id}
              onClick={() => handleSelect(p.id)}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-hover transition-colors text-left"
            >
              <Avatar profile={p} size="sm" />
              <span className="text-sm text-primary">{p.name}</span>
            </button>
          ))}
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
        <button onClick={onClose} className="mt-4 w-full py-2 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}

function PasswordPanel({ profile, onDone, minPasswordLength }: { profile: Profile; onDone: () => void; minPasswordLength: number }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const nextError = next.length > 0 ? validatePassword(next, minPasswordLength) : "";
  const canSubmit = !saving && !!current && !!next && !validatePassword(next, minPasswordLength);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
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
          <div className="flex flex-col gap-1">
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              placeholder="New password"
              className={cn(
                "bg-input border rounded-xl px-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none transition-colors",
                nextError ? "border-red-400 focus:border-red-400" : "border-border focus:border-accent/60",
              )}
            />
            {nextError && <p className="text-xs text-red-400">{nextError}</p>}
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onDone} className="flex-1 py-2.5 rounded-xl border border-border text-sm text-secondary hover:text-primary hover:bg-hover transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={!canSubmit} className="flex-1 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

