export function sourceLink(documentId: number, page: number, chunkId?: number, workspace?: number | string) {
  const scope = workspace ? `&workspace=${workspace}` : "";
  const chunk = chunkId && Number.isSafeInteger(chunkId) && chunkId > 0 ? `&chunk=${chunkId}` : "";
  return `#paper=${documentId}&page=${page}${scope}${chunk}`;
}
