import { useState, type CSSProperties } from 'react'
import type { Analysis, BBox, JobImage } from '../api/types'
import { formatPercent } from '../lib/format'
import styles from './PhotoAnnotations.module.css'

/** 이보다 확률이 낮은 표기는 주황 박스 + 확률 배지 (3단계 통과 기준 80과 같게) */
const LOW_PROB = 0.8

interface Mark {
  id: string
  /** 해석에 쓴 글자 또는 기호 code (2단계가 VLM 읽기를 썼으면 그 값) */
  value: string
  kind: 'text' | 'symbol'
  /** ocr: 1단계가 찾음 / vlm: 1단계가 놓치고 VLM 만 읽음 (v*) */
  source: 'ocr' | 'vlm'
  /** 1단계 확률 (VLM 만 읽은 표기는 없음) */
  prob?: number
  bbox: BBox
  candidates?: { text: string; prob: number }[]
  /** 1단계가 읽은 값 — 2단계가 VLM 읽기로 바꿨을 때만 */
  ocrValue?: string
}

interface PhotoAnnotationsProps {
  /** 사진 파일 주소 (jobImageUrl) */
  src: string
  image: JobImage
  /** 이 사진의 가장 최근 해석 결과. 없으면 사진만 보여 준다. */
  analysis: Analysis | undefined
}

/**
 * 사진 위에 1단계가 찾은 글자·기호와 VLM 만 읽은 표기(v*, 위치를 알려 준 것)를 박스로 표시한다
 * (좌표는 원본 픽셀, 화면 크기에 맞춰 % 로 바꿈 — 1단계 보정본을 보여 줘도 비율이 같아 그대로 맞음).
 * 박스를 누르면 사진 아래에 읽은 값·확률·후보를 보여 준다. 사진을 덜 가리도록 사진 위에는 확률이 낮은 박스의 확률 배지만 얹는다.
 */
export function PhotoAnnotations({ src, image, analysis }: PhotoAnnotationsProps) {
  const [selectedId, setSelectedId] = useState<string>()
  const vision = analysis?.vision
  const reading = analysis?.context.vlm?.reading
  // 2단계가 1단계 대신 쓴 VLM 읽기 (used)
  const used = new Map(
    [...(reading?.texts ?? []).map((x) => [x.ref_id, x.text, x.used] as const), ...(reading?.symbols ?? []).map((x) => [x.ref_id, x.label, x.used] as const)]
      .filter(([, , isUsed]) => isUsed)
      .map(([id, value]) => [id, value]),
  )
  const marks: Mark[] = vision
    ? [
        ...vision.texts.map((t) => ({
          id: t.id, value: used.get(t.id) ?? t.text, ocrValue: used.has(t.id) ? t.text : undefined,
          kind: 'text' as const, source: 'ocr' as const, prob: t.prob, bbox: t.bbox, candidates: t.candidates,
        })),
        ...vision.symbols.map((s) => ({
          id: s.id, value: used.get(s.id) ?? s.label, ocrValue: used.has(s.id) ? s.label : undefined,
          kind: 'symbol' as const, source: 'ocr' as const, prob: s.prob, bbox: s.bbox,
        })),
        ...(reading?.texts ?? []).flatMap((x) =>
          x.ref_id.startsWith('v') && x.bbox ? [{ id: x.ref_id, value: x.text, kind: 'text' as const, source: 'vlm' as const, bbox: x.bbox }] : [],
        ),
        ...(reading?.symbols ?? []).flatMap((x) =>
          x.ref_id.startsWith('v') && x.bbox ? [{ id: x.ref_id, value: x.label, kind: 'symbol' as const, source: 'vlm' as const, bbox: x.bbox }] : [],
        ),
      ]
    : []
  const vlmCount = marks.filter((mark) => mark.source === 'vlm').length
  // bbox 는 1단계가 받은 원본 크기 기준 (사진 메타데이터와 같아야 하지만, 해석 결과의 값을 우선한다)
  const width = vision?.image_size.width ?? image.width
  const height = vision?.image_size.height ?? image.height
  const selected = marks.find((mark) => mark.id === selectedId)

  return (
    <figure className={styles.figure}>
      {/* 높이 상한(520px) 안에서도 사진 비율 그대로 — 레터박스가 생기면 % 박스 위치가 어긋남 */}
      <div
        className={styles.frame}
        style={{ aspectRatio: `${image.width} / ${image.height}`, '--ratio': image.width / image.height } as CSSProperties}
      >
        <img className={styles.photo} src={src} alt={`올린 사진 ${image.filename}`} />
        {marks.map((mark) => {
          const [x1, y1, x2, y2] = mark.bbox
          const low = mark.prob !== undefined && mark.prob < LOW_PROB
          return (
            <button
              key={mark.id}
              type="button"
              className={styles.box}
              data-kind={mark.kind}
              data-source={mark.source}
              data-low={low || undefined}
              // 배지가 사진 위쪽 끝에서 잘리지 않게, 박스가 위쪽에 붙어 있으면 박스 아래에 단다
              data-badge-below={(low && y1 / height < 0.08) || undefined}
              aria-pressed={mark.id === selectedId}
              aria-label={`${mark.kind === 'text' ? '글자' : '기호'} ${mark.value}, ${
                mark.prob === undefined ? 'VLM 만 읽음' : `확률 ${formatPercent(mark.prob * 100)}`
              }`}
              style={{
                left: `${(x1 / width) * 100}%`,
                top: `${(y1 / height) * 100}%`,
                width: `${((x2 - x1) / width) * 100}%`,
                height: `${((y2 - y1) / height) * 100}%`,
              }}
              onClick={() => setSelectedId(mark.id === selectedId ? undefined : mark.id)}
            >
              {low && (
                <span className={styles.badge} aria-hidden="true">
                  {formatPercent((mark.prob ?? 0) * 100)}
                </span>
              )}
            </button>
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
            {selected.prob === undefined ? (
              <span>1단계가 놓치고 VLM 만 읽음</span>
            ) : (
              <span>
                {selected.ocrValue ? `1단계는 '${selected.ocrValue}'로 읽음 · ` : ''}확률 {formatPercent(selected.prob * 100)}
              </span>
            )}
            {selected.candidates && selected.candidates.length > 1 && (
              <span>
                후보 {selected.candidates.map((c) => `${c.text} (${formatPercent(c.prob * 100)})`).join(', ')}
              </span>
            )}
          </>
        ) : (
          `글자 ${vision?.texts.length ?? 0}개, 기호 ${vision?.symbols.length ?? 0}개를 찾았어요${
            vlmCount ? ` (점선 ${vlmCount}개는 VLM 만 읽은 것)` : ''
          }. 박스를 누르면 읽은 값을 보여 줘요.`
        )}
      </figcaption>
    </figure>
  )
}
