import { useCallback, useEffect, useRef, useState } from 'react'

export interface PreviewFile {
  file: File
  /** 미리보기용 object URL */
  url: string
}

/**
 * 고른 파일 목록 + 미리보기용 object URL. 고를 때 URL 을 만들고, 뺄 때와 언마운트될 때 해제한다.
 *
 * @example
 * const [photos, addPhotos, removePhoto] = usePreviewFiles()
 * <input type="file" multiple onChange={(e) => addPhotos(Array.from(e.target.files ?? []))} />
 */
export function usePreviewFiles(): [
  files: PreviewFile[],
  add: (files: File[]) => void,
  remove: (index: number) => void,
] {
  const [files, setFiles] = useState<PreviewFile[]>([])
  const filesRef = useRef(files)

  useEffect(() => {
    filesRef.current = files
  }, [files])

  useEffect(() => () => filesRef.current.forEach(({ url }) => URL.revokeObjectURL(url)), [])

  const add = useCallback((picked: File[]) => {
    const added = picked.map((file) => ({ file, url: URL.createObjectURL(file) }))
    setFiles((current) => [...current, ...added])
  }, [])

  const remove = useCallback((index: number) => {
    const target = filesRef.current[index]
    if (target) URL.revokeObjectURL(target.url)
    setFiles((current) => current.filter((_, i) => i !== index))
  }, [])

  return [files, add, remove]
}
