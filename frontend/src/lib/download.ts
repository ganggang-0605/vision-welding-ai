/** 값을 JSON 파일로 내려받는다 (Blob + 임시 <a download>). */
export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // 일부 브라우저는 click 직후 해제하면 다운로드가 취소되므로 한 틱 늦춘다.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
