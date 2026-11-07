export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function backupFilename(exportedAt: string): string {
  const day = exportedAt.slice(0, 10);
  return `fitness-backup-${day}.json`;
}
