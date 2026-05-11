import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DatabaseIcon,
  DownloadIcon,
  LoaderIcon,
  PlusIcon,
  RefreshCwIcon,
  Trash2Icon,
  UploadIcon,
  XIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { formatBytes } from "../lib/utils";
import type { Dataset } from "../types";
import { cn } from "../lib/utils";

const DATASET_ACCEPT = ".txt,.md,.csv,.json,.pdf,.xls,.xlsx,.docx,.pptx";

function fmtDate(iso: string) {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export default function DatasetManager({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [uploadingFor, setUploadingFor] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: datasets = [], isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: api.listDatasets,
  });

  const createMut = useMutation({
    mutationFn: () => api.createDataset(newName.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setCreating(false);
      setNewName("");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.deleteDataset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });

  const reindexMut = useMutation({
    mutationFn: (id: number) => api.reindexDataset(id),
  });

  const deleteFileMut = useMutation({
    mutationFn: ({ datasetId, fileId }: { datasetId: number; fileId: number }) =>
      api.deleteDatasetFile(datasetId, fileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });

  const uploadFileMut = useMutation({
    mutationFn: ({ datasetId, file }: { datasetId: number; file: File }) =>
      api.uploadDatasetFile(datasetId, file),
    onSuccess: async (_data, { datasetId }) => {
      await qc.invalidateQueries({ queryKey: ["datasets"] });
      setUploadingFor(null);
      // expand the card so the new file is immediately visible
      setExpanded((prev) => new Set(prev).add(datasetId));
    },
    onError: () => setUploadingFor(null),
  });

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function handleUploadClick(datasetId: number) {
    setUploadingFor(datasetId);
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || uploadingFor === null) return;
    uploadFileMut.mutate({ datasetId: uploadingFor, file });
    e.target.value = "";
  }

  return (
    <div className="flex flex-col h-full bg-canvas" data-testid="dataset-manager">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border/50 flex-shrink-0">
        <div className="flex items-center gap-2">
          <DatabaseIcon size={16} className="text-accent" />
          <h2 className="text-sm font-semibold text-primary">Datasets</h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCreating(true)}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white transition-colors"
            title="New dataset"
          >
            <PlusIcon size={13} />
            New
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
            aria-label="Close"
          >
            <XIcon size={16} />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* new dataset form */}
        {creating && (
          <div className="bg-elevated border border-border rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-primary">New dataset</p>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Dataset name"
              className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm text-primary placeholder-muted outline-none focus:border-accent/60 transition-colors"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setCreating(false); setNewName(""); }}
                className="text-xs px-3 py-1.5 rounded-lg text-muted hover:text-primary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!newName.trim() || createMut.isPending}
                className="text-xs px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white disabled:opacity-50 transition-colors"
              >
                {createMut.isPending ? "Creating…" : "Create"}
              </button>
            </div>
          </div>
        )}

        {isLoading && (
          <p className="text-sm text-muted text-center py-8">Loading…</p>
        )}

        {!isLoading && datasets.length === 0 && !creating && (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
            <DatabaseIcon size={28} className="text-muted opacity-40" />
            <p className="text-sm text-muted">No datasets yet</p>
            <p className="text-xs text-muted opacity-70">Create a dataset to upload files for RAG retrieval</p>
          </div>
        )}

        {datasets.map((ds: Dataset) => (
          <DatasetCard
            key={ds.id}
            dataset={ds}
            expanded={expanded.has(ds.id)}
            onToggle={() => toggleExpand(ds.id)}
            onUpload={() => handleUploadClick(ds.id)}
            onDelete={() => deleteMut.mutate(ds.id)}
            onReindex={() => reindexMut.mutate(ds.id)}
            onDeleteFile={(fileId) => deleteFileMut.mutate({ datasetId: ds.id, fileId })}
            onDownloadFile={(fileId, filename) => api.downloadDatasetFile(ds.id, fileId, filename)}
            uploading={uploadingFor === ds.id && uploadFileMut.isPending}
            reindexing={reindexMut.isPending}
          />
        ))}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={DATASET_ACCEPT}
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
}

function IndexStatusBadge({ status, chunks }: { status: Dataset["index_status"]; chunks: number }) {
  if (status === "indexing") {
    return (
      <span className="flex items-center gap-1 text-[0.65rem] text-accent" title="Indexing…">
        <LoaderIcon size={11} className="animate-spin" />
        indexing
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex items-center gap-1 text-[0.65rem] text-red-400" title="Indexing failed — try reindexing">
        <AlertCircleIcon size={11} />
        failed
      </span>
    );
  }
  if (chunks > 0) {
    return (
      <span className="flex items-center gap-1 text-[0.65rem] text-green-400" title={`${chunks} chunks indexed`}>
        <CheckCircleIcon size={11} />
        {chunks} chunks
      </span>
    );
  }
  return null;
}

function DatasetCard({
  dataset,
  expanded,
  onToggle,
  onUpload,
  onDelete,
  onReindex,
  onDeleteFile,
  onDownloadFile,
  uploading,
  reindexing,
}: {
  dataset: Dataset;
  expanded: boolean;
  onToggle: () => void;
  onUpload: () => void;
  onDelete: () => void;
  onReindex: () => void;
  onDeleteFile: (fileId: number) => void;
  onDownloadFile: (fileId: number, filename: string) => void;
  uploading: boolean;
  reindexing: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className="bg-elevated border border-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3">
        <button onClick={onToggle} className="flex items-center gap-2 flex-1 min-w-0 text-left">
          {expanded ? (
            <ChevronDownIcon size={14} className="text-muted flex-shrink-0" />
          ) : (
            <ChevronRightIcon size={14} className="text-muted flex-shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium text-primary truncate">{dataset.name}</p>
            <div className="flex items-center gap-2">
              <p className="text-[0.7rem] text-muted">
                {dataset.files.length} file{dataset.files.length !== 1 ? "s" : ""}
              </p>
              <IndexStatusBadge status={dataset.index_status} chunks={dataset.indexed_chunks} />
            </div>
          </div>
        </button>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={onUpload}
            disabled={uploading}
            title="Upload file"
            className="p-2 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors disabled:opacity-40"
          >
            <UploadIcon size={20} />
          </button>
          <button
            onClick={onReindex}
            disabled={reindexing}
            title="Reindex"
            className={cn(
              "p-2 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors disabled:opacity-40",
              reindexing && "animate-spin",
            )}
          >
            <RefreshCwIcon size={20} />
          </button>
          {confirmDelete ? (
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted">Delete?</span>
              <button
                onClick={onDelete}
                className="text-sm text-red-400 hover:text-red-300 font-medium px-2"
              >
                Yes
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="text-sm text-muted hover:text-primary font-medium px-2"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              title="Delete dataset"
              className="p-2 rounded-lg hover:bg-hover text-muted hover:text-red-400 transition-colors"
            >
              <Trash2Icon size={20} />
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 py-2 space-y-1">
          {dataset.files.length === 0 ? (
            <p className="text-xs text-muted py-2 text-center">No files — upload one to get started</p>
          ) : (
            dataset.files.map((f) => (
              <div key={f.id} className="flex items-center gap-2 py-1.5 group">
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-primary truncate">{f.filename}</p>
                  <p className="text-[0.7rem] text-muted">{formatBytes(f.size)} · {fmtDate(f.created_at)}</p>
                </div>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={() => onDownloadFile(f.id, f.filename)}
                    title="Download file"
                    className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
                  >
                    <DownloadIcon size={20} />
                  </button>
                  <button
                    onClick={() => onDeleteFile(f.id)}
                    title="Remove file"
                    className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-red-400 transition-colors"
                  >
                    <Trash2Icon size={20} />
                  </button>
                </div>
              </div>
            ))
          )}
          {uploading && (
            <p className="text-xs text-muted py-1 text-center">Uploading…</p>
          )}
        </div>
      )}
    </div>
  );
}
