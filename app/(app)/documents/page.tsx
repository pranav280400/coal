"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtBytes, fmtDateTime, humanize, processingTone } from "@/lib/format";
import type { DocumentItem, DocumentType, Page } from "@/lib/types";

const TYPES: DocumentType[] = ["statutory_return", "inspection_report", "permit", "license", "circular", "regulation", "evidence", "other"];

export default function DocumentsPage() {
  const { can } = useSession();
  const qc = useQueryClient();
  const [filters, setFilters] = useState({ mine_id: "", doc_type: "", status: "", q: "" });
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [up, setUp] = useState({ title: "", doc_type: "other" as DocumentType, mine_id: "", language: "eng+hin" });
  const [file, setFile] = useState<File | null>(null);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["documents", filters, page],
    queryFn: () => api<Page<DocumentItem>>("/documents", { query: { ...filters, page, size: 20 } }),
    refetchInterval: (q) => (q.state.data?.items.some((d) => d.ocr_status === "pending" || d.ocr_status === "processing") ? 5000 : false),
  });
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file!);
      form.append("title", up.title || file!.name);
      form.append("doc_type", up.doc_type);
      form.append("language", up.language);
      if (up.mine_id) form.append("mine_id", up.mine_id);
      return api<DocumentItem>("/documents", { method: "POST", form });
    },
    onSuccess: () => {
      toast.success("Uploaded — the document is being read and will be searchable shortly");
      setOpen(false);
      setFile(null);
      setUp((u) => ({ ...u, title: "" }));
      void qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const upd = (k: keyof typeof filters) => (v: string) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };
  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle="Upload scanned papers — the text is read automatically and becomes searchable"
        actions={can("document:write") && <Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Upload document</Button>}
      />
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-4">
          <MineSelect allowAll value={filters.mine_id} onChange={upd("mine_id")} />
          <Select value={filters.doc_type} onChange={(e) => upd("doc_type")(e.target.value)} aria-label="Type">
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </Select>
          <Select value={filters.status} onChange={(e) => upd("status")(e.target.value)} aria-label="Processing status">
            <option value="">All statuses</option>
            {["pending", "processing", "completed", "failed"].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </Select>
          <Input placeholder="Search title or text…" value={filters.q} onChange={(e) => upd("q")(e.target.value)} />
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<FileText className="h-6 w-6" />} title="No documents" body="Upload scanned statutory returns, permits or legacy records to digitise them." />
        ) : (
          <>
            <Table>
              <thead><tr><Th>Document</Th><Th>Type</Th><Th>Size</Th><Th>Digitisation</Th><Th>Uploaded</Th></tr></thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.id} className="hover:bg-fg/5/60">
                    <Td>
                      <Link href={`/documents/${d.id}`} className="block font-medium hover:text-copper-400">{d.title}</Link>
                      <span className="text-xs text-muted">{d.filename}</span>
                    </Td>
                    <Td>{humanize(d.doc_type)}</Td>
                    <Td>{fmtBytes(d.size_bytes)}{d.page_count ? ` · ${d.page_count}p` : ""}</Td>
                    <Td>
                      <Badge tone={processingTone[d.ocr_status]}>{humanize(d.ocr_status)}</Badge>
                      {d.embedded_chunks > 0 && <span className="ml-2 text-xs text-muted">{d.embedded_chunks} chunks indexed</span>}
                    </Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(d.created_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Upload document">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (file) upload.mutate(); }} className="space-y-4">
          <Field label="File" required hint="PDF, JPEG, PNG, TIFF or text — max 25 MB">
            <Input type="file" accept="application/pdf,image/*,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required className="py-2" />
          </Field>
          <Field label="Title"><Input value={up.title} onChange={(e) => setUp((u) => ({ ...u, title: e.target.value }))} placeholder={file?.name} /></Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Type">
              <Select value={up.doc_type} onChange={(e) => setUp((u) => ({ ...u, doc_type: e.target.value as DocumentType }))}>
                {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            </Field>
            <Field label="Document language">
              <Select value={up.language} onChange={(e) => setUp((u) => ({ ...u, language: e.target.value }))}>
                <option value="eng+hin">English + Hindi</option>
                <option value="eng">English</option>
                <option value="hin">Hindi</option>
              </Select>
            </Field>
          </div>
          <Field label="Mine" hint="Leave empty for organisation-wide circulars"><MineSelect allowAll value={up.mine_id} onChange={(v) => setUp((u) => ({ ...u, mine_id: v }))} /></Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={upload.isPending} disabled={!file}><Upload className="h-4 w-4" /> Upload</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
