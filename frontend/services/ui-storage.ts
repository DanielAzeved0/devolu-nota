import type { ReturnNotePublic } from "@/types/api";

const notesPrefix = "devolu.returnNotes.";

export function getStoredReturnNotes(companyId: string): ReturnNotePublic[] {
  if (typeof window === "undefined") {
    return [];
  }
  const raw = localStorage.getItem(`${notesPrefix}${companyId}`);
  if (!raw) {
    return [];
  }
  try {
    return JSON.parse(raw) as ReturnNotePublic[];
  } catch {
    return [];
  }
}

export function storeReturnNote(companyId: string, note: ReturnNotePublic) {
  const currentNotes = getStoredReturnNotes(companyId);
  const nextNotes = [note, ...currentNotes.filter((item) => item.id !== note.id)].slice(0, 50);
  localStorage.setItem(`${notesPrefix}${companyId}`, JSON.stringify(nextNotes));
}

export function replaceStoredReturnNotes(companyId: string, notes: ReturnNotePublic[]) {
  localStorage.setItem(`${notesPrefix}${companyId}`, JSON.stringify(notes.slice(0, 50)));
}
