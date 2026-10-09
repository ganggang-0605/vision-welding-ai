import { useState } from 'react'
import type { Analysis, BBox, JobImage } from '../api/types'
import { formatPercent } from '../lib/format'
import styles from './PhotoAnnotations.module.css'

interface Mark {
  id: string
  /** 읽은 글자 또는 기호 code */
  value: string
  kind: 'text' | 'symbol'
  prob: number
  bbox: BBox
  candidates?: { text: string; prob: number }[]
}

interface PhotoAnnotationsProps {
  /** 사진 파일 주소 (jobImageUrl) */
  src: string
  image: JobImage
  /** 이 사진의 가장 최근 해석 결과. 없으면 사진만 보여 준다. */
  analysis: Analysis | undefined
}

/**
 * 사진 위에 1단계가 찾은 글자·기호 위치를 박스로 표시한다 (좌표는 원본 픽셀, 화면 크기에 맞춰 % 로 바꿈).
 * 박스를 누르면 사진 아래에 읽은 값·확률·후보를 보여 준다. 라벨을 사진 위에 얹지 않아 사진을 가리지 않는다.
 */
export function PhotoAnnotations({ src, image, analysis }: PhotoAnnotationsProps) {
  const [selectedId, setSelectedId] = useState<string>()
  const vision = analysis?.vision
  const marks: Mark[] = vision
    ? [
        ...vision.texts.map((t) => ({ id: t.id, value: t.text, kind: 'text' as const, prob: t.prob, bbox: t.bbox, candidates: t.candidates })),
        ...vision.symbols.map((s) => ({ id: s.id, value: s.label, kind: 'symbol' as const, prob: s.prob, bbox: s.bbox })),
      ]
    : []
  // bbox 는 1단계가 받은 원본 크기 기준 (사진 메타데이터와 같아야 하지만, 해석 결과의 값을 우선한다)
  const width = vision?.image_size.width ?? image.width
  const height = vision?.image_size.height ?? image.height
  const selected = marks.find((mark) => mark.id === selectedId)

  return (
    <figure className={styles.figure}>
      <div className={styles.frame} style={{ aspectRatio: `${image.width} / ${image.height}` }}>
        <img className={styles.photo} src={src} alt={`올린 사진 ${image.filename}`} />
        {marks.map((mark) => {
          const [x1, y1, x2, y2] = mark.bbox
          return (
            <button
              key={mark.id}
              type="button"
              className={styles.box}
              data-kind={mark.kind}
              data-low={mark.prob < 0.8 || undefined}
              aria-pressed={mark.id === selectedId}
              aria-label={`${mark.kind === 'text' ? '글자' : '기호'} ${mark.value}, 확률 ${formatPercent(mark.prob * 100)}`}
              style={{
                left: `${(x1 / width) * 100}%`,
                top: `${(y1 / height) * 100}%`,
                width: `${((x2 - x1) / width) * 100}%`,
                height: `${((y2 - y1) / height) * 100}%`,
              }}
              onClick={() => setSelectedId(mark.id === selectedId ? undefined : mark.id)}
            />
          )
        })}
      </div>
      <figcaption className={styles.caption}>
        {!analysis ? (
          '아직 해석하지 않은 사진이에요.'
        ) : marks.length === 0 ? (
          '이 사진에서 찾은 글자·기호가 없어요.'
        ) : selected ? (
          <>
            <span className="mono">{selected.id}</span>
            <strong>{selected.value}</strong>
            <span>{selected.kind === 'text' ? '글자' : '기호'}</span>
            <span>확률 {formatPercent(selected.prob * 100)}</span>
            {selected.candidates && selected.candidates.length > 1 && (
              <span>후보 {selected.candidates.map((c) => c.text).join(', ')}</span>
            )}
          </>
        ) : (
          `글자 ${vision?.texts.length ?? 0}개, 기호 ${vision?.symbols.length ?? 0}개를 찾았어요. 박스를 누르면 읽은 값을 보여 줘요.`
        )}
      </figcaption>
    </figure>
  )
}
