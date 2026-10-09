import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * File/Blob 미리보기용 object URL.
 * setBlob 으로 바꾸면 이전 URL 을 바로 해제하고, 언마운트될 때 마지막 URL 도 해제한다.
 *
 * @example
 * const [previewUrl, setPreviewBlob] = useObjectUrl()
 * <input type="file" onChange={(e) => setPreviewBlob(e.target.files?.[0])} />
 */
export function useObjectUrl(): [url: string | undefined, setBlob: (blob: Blob | undefined) => void] {
  const [url, setUrl] = useState<string>()
  const urlRef = useRef<string>(undefined)

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    },
    [],
  )

  const setBlob = useCallback((blob: Blob | undefined) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = blob ? URL.createObjectURL(blob) : undefined
    setUrl(urlRef.current)
  }, [])

  return [url, setBlob]
}
