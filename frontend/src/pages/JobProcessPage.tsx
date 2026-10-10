import { CaretRight, Check, Info, WarningCircle } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { jobImageUrl, listAnalyses, listJobImages } from '../api/jobs'
import { getPipelineStatus } from '../api/pipeline'
import type { Analysis, ConfidenceLayer, Conflict, Job, PipelineStatus } from '../api/types'
import { CellView } from '../components/CellView'
import { JobFrame } from '../components/JobFrame'
import { LegLengthList } from '../components/LegLengthList'
import { ErrorNotice, Notice } from '../components/Notice'
import { PhotoAnnotations } from '../components/PhotoAnnotations'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { formatDateTime, formatScore } from '../lib/format'
import {
  ASSEMBLY_LEVEL_LABEL,
  CONFLICT_LABEL,
  jointTypeLabel,
  MATCH_LABEL,
  positionLabel,
  PREPROCESS_STEP_LABEL,
  REVIEW_REASON_LABEL,
  VLM_PROVIDER_LABEL,
  WELDING_SOURCE_LABEL,
  withUnit,
} from '../lib/labels'
import { paths, type ProcessStage } from '../lib/paths'
import styles from './JobProcessPage.module.css'

const STAGES: { key: ProcessStage; step: number; title: string }[] = [
  { key: 'vision', step: 1, title: '시각 인식' },
  { key: 'context', step: 2, title: 'DB 기반 맥락 해석' },
  { key: 'confidence', step: 3, title: '신뢰도 산출' },
]

/**
 * 해석 과정 — 표기 정보 해석 프로세스의 1·2·3단계를 단계별로 자세히 (shared/schemas 의 Analysis 그대로).
 * 위쪽 단계 표시에서 고르고, 사진이 여러 장이거나 작업자 확인으로 다시 해석했으면 어떤 해석을 볼지 고른다 (?analysis=).
 */
export function JobProcessPage() {
  return <JobFrame section="해석 과정">{(job) => <Process job={job} />}</JobFrame>
}

function Process({ job }: { job: Job }) {
  const workspace = useWorkspace()
  const params = useParams()
  const stage = STAGES.find((s) => s.key === params.stage)?.key ?? 'vision'
  const [searchParams, setSearchParams] = useSearchParams()
  const analyses = useAsync((signal) => listAnalyses(workspace.id, job.id, signal), [workspace.id, job.id])
  const images = useAsync((signal) => listJobImages(workspace.id, job.id, signal), [workspace.id, job.id])
  const status = useAsync((signal) => getPipelineStatus(signal), [])

  if (analyses.error !== undefined) return <ErrorNotice error={analyses.error} onRetry={analyses.reload} />
  if (!analyses.data) return <div className={styles.placeholder} aria-label="불러오는 중" />
  if (analyses.data.length === 0) {
    return (
      <Notice
        title="아직 해석하지 않은 작업이에요"
        action={
          <Link className="btn" to={paths.job(workspace.id, job.id)}>
            사진 올리러 가기
          </Link>
        }
      >
        해석 결과 화면에서 사진을 올리고 해석을 시작하면 단계별 과정을 여기서 볼 수 있어요.
      </Notice>
    )
  }

  const list = analyses.data
  const analysis = list.find((a) => a.analysis_id === searchParams.get('analysis')) ?? list[list.length - 1]
  const image = images.data?.find((i) => i.image_id === analysis.image_id)
  const imageIndex = images.data ? images.data.findIndex((i) => i.image_id === analysis.image_id) + 1 : 0
  const stageLink = (key: ProcessStage) => {
    const query = searchParams.toString()
    return paths.jobProcess(workspace.id, job.id, key) + (query ? `?${query}` : '')
  }

  return (
    <>
      <div className={styles.toolbar}>
        <nav className={styles.stepper} aria-label="해석 단계">
          {STAGES.map((s, index) => (
            <div key={s.key} className={styles.stepItem}>
              {index > 0 && <CaretRight className={styles.stepArrow} size={14} weight="bold" aria-hidden="true" />}
              <Link className={styles.step} to={stageLink(s.key)} aria-current={s.key === stage ? 'step' : undefined}>
                <span className={styles.stepNumber}>{s.step}</span>
                <span className={styles.stepText}>
                  <span className={styles.stepTitle}>{s.title}</span>
                  <span className={styles.stepSummary}>{stageSummary(s.key, analysis)}</span>
                </span>
              </Link>
            </div>
          ))}
        </nav>
        {list.length > 1 && (
          <label className={styles.picker}>
            <span className="visually-hidden">볼 해석 결과</span>
            <select
              className="input"
              value={analysis.analysis_id}
              onChange={(event) => setSearchParams({ analysis: event.target.value }, { replace: true })}
            >
              {list.map((a) => (
                <option key={a.analysis_id} value={a.analysis_id}>
                  {analysisLabel(a, images.data?.findIndex((i) => i.image_id === a.image_id) ?? -1)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <p className={styles.meta}>
        {imageIndex > 0 ? `${imageIndex}번째 사진` : '사진'}, {analysis.revision === 1 ? '처음 해석' : `작업자 확인 후 ${analysis.revision}차 해석`},{' '}
        {formatDateTime(analysis.created_at)}
      </p>

      {stage === 'vision' && (
        <VisionStage
          analysis={analysis}
          status={status.data}
          photo={
            image && (
              <PhotoAnnotations
                key={analysis.analysis_id}
                src={jobImageUrl(workspace.id, job.id, image.image_id)}
                image={image}
                analysis={analysis}
              />
            )
          }
        />
      )}
      {stage === 'context' && <ContextStage analysis={analysis} status={status.data} />}
      {stage === 'confidence' && <ConfidenceStage analysis={analysis} />}
    </>
  )
}

function analysisLabel(analysis: Analysis, imageIndex: number): string {
  const photo = imageIndex >= 0 ? `${imageIndex + 1}번째 사진` : '사진'
  return `${photo}, ${analysis.revision === 1 ? '처음 해석' : `${analysis.revision}차 해석`}`
}

/** 단계 표시 아래의 한 줄 요약 */
function stageSummary(stage: ProcessStage, analysis: Analysis): string {
  const { vision, context, confidence } = analysis
  if (stage === 'vision') return `글자 ${vision.texts.length}개, 기호 ${vision.symbols.length}개`
  if (stage === 'context') {
    const matched = context.dictionary_matches.filter((m) => m.code).length
    const legs = context.leg_lengths?.length ? `, 각장 ${context.leg_lengths.length}개` : ''
    return `사전 ${matched}/${context.dictionary_matches.length}, 부재 ${context.part.found_in_tree ? '찾음' : '못 찾음'}${legs}`
  }
  return confidence ? `종합 ${formatScore(confidence.overall)}%, ${confidence.passed ? '통과' : '확인 필요'}` : '아직 없음'
}

/** 0~1 확률 → "62%", 모르면 '-' */
function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '-' : `${Math.round(value * 100)}%`
}

// ── 공통 조각 ──

function Block({ letter, title, description, children }: { letter: string; title: string; description: string; children: ReactNode }) {
  return (
    <section className={styles.block} aria-label={`${letter}. ${title}`}>
      <header className={styles.blockHead}>
        <span className={styles.letter} aria-hidden="true">
          {letter}
        </span>
        <div>
          <h2 className={styles.blockTitle}>{title}</h2>
          <p className={styles.blockDesc}>{description}</p>
        </div>
      </header>
      {children}
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="group-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function Refs({ ids }: { ids: string[] | undefined }) {
  if (!ids || ids.length === 0) return null
  return <span className={styles.refs}>{ids.join(', ')}</span>
}

// ── 1단계 시각 인식 ──

function VisionStage({ analysis, status, photo }: { analysis: Analysis; status: PipelineStatus | undefined; photo: ReactNode }) {
  const { vision } = analysis
  const models = Object.entries(vision.models ?? {})
  return (
    <>
      {photo && <div className={styles.photo}>{photo}</div>}

      <Block letter="a" title="전처리" description="노이즈·오염·스크래치를 줄여 글자를 읽기 쉽게 만들어요.">
        <dl className="group">
          <Row label="전체 보정 강도">{pct(vision.preprocess.correction_strength)}</Row>
          {vision.preprocess.steps.length === 0 ? (
            <Row label="적용한 보정">없음</Row>
          ) : (
            vision.preprocess.steps.map((step) => (
              <Row key={step.name} label={PREPROCESS_STEP_LABEL[step.name] ?? step.name}>
                강도 {pct(step.strength)}
              </Row>
            ))
          )}
          {vision.elapsed_ms !== undefined && <Row label="1단계 걸린 시간">{(vision.elapsed_ms / 1000).toFixed(1)}초</Row>}
        </dl>
      </Block>

      <Block letter="b" title="OCR 문자 인식" description="글자를 찾고 읽어요. 확률이 낮은 글자는 후보를 함께 남겨요.">
        {status && !status.ocr_available && (
          <Notice tone="warning">문자 인식 모델(PaddleOCR)이 설치되지 않아 이 단계를 건너뛰었어요.</Notice>
        )}
        {models.length > 0 && <p className={styles.models}>{models.map(([k, v]) => `${k} ${v}`).join(', ')}</p>}
        {vision.texts.length === 0 ? (
          <p className="state">읽은 글자가 없어요.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">읽은 글자</th>
                  <th scope="col" className="num">
                    확률
                  </th>
                  <th scope="col">후보</th>
                  <th scope="col">모델</th>
                </tr>
              </thead>
              <tbody>
                {vision.texts.map((t) => (
                  <tr key={t.id}>
                    <td className="code">{t.id}</td>
                    <td className="code">
                      <CharProbs text={t.text} probs={t.char_probs} />
                    </td>
                    <td className={`num ${t.prob < 0.8 ? styles.low : ''}`}>{pct(t.prob)}</td>
                    <td className="secondary">{t.candidates?.slice(1).map((c) => c.text).join(', ')}</td>
                    <td className="secondary">{t.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Block>

      <Block letter="c" title="YOLO 기호 인식" description="현장 용접 표시 같은 기호와 그림을 찾아요.">
        {status && !status.symbol_detector_available && vision.symbols.length === 0 && (
          <Notice>기호 검출 모델(YOLO)은 아직 연결 전이에요.</Notice>
        )}
        {vision.symbols.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">기호</th>
                  <th scope="col" className="num">
                    확률
                  </th>
                  <th scope="col">모델</th>
                </tr>
              </thead>
              <tbody>
                {vision.symbols.map((s) => (
                  <tr key={s.id}>
                    <td className="code">{s.id}</td>
                    <td className="code">{s.label}</td>
                    <td className={`num ${s.prob < 0.8 ? styles.low : ''}`}>{pct(s.prob)}</td>
                    <td className="secondary">{s.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Block>
    </>
  )
}

/** 글자별 확률이 있으면 낮은(80% 미만) 글자를 주황으로 */
function CharProbs({ text, probs }: { text: string; probs: number[] | undefined }) {
  if (!probs || probs.length !== text.length) return <>{text}</>
  return (
    <>
      {[...text].map((ch, i) => (
        <span key={i} className={probs[i] < 0.8 ? styles.low : undefined} title={pct(probs[i])}>
          {ch}
        </span>
      ))}
    </>
  )
}

// ── 2단계 DB 기반 맥락 해석 ──

function ContextStage({ analysis, status }: { analysis: Analysis; status: PipelineStatus | undefined }) {
  const { context } = analysis
  const wc = context.welding_condition
  return (
    <>
      {context.user_context && (
        <Notice title="작업자가 덧붙인 맥락">{context.user_context}</Notice>
      )}

      <Block letter="a" title="용접 기준 DB" description="표준 용접 기준표와 대조해 용접 조건을 골라요.">
        {wc ? (
          <dl className="group">
            <Row label="이음 형태">{jointTypeLabel(wc.joint_type)}</Row>
            <Row label="공법, 자세">
              {wc.process}, {positionLabel(wc.position)}
            </Row>
            <Row label="판 두께">{wc.thickness_mm != null ? `${wc.thickness_mm}mm` : '-'}</Row>
            {wc.leg_length_mm != null && <Row label="각장 (기준 행을 고른 값)">{wc.leg_length_mm}mm</Row>}
            <Row label="전류, 전압, 속도">
              {withUnit(wc.current_a, 'A')}, {withUnit(wc.voltage_v, 'V')}, {withUnit(wc.speed_cm_min, 'cm/min')}
            </Row>
            <Row label="기준표와 일치">{wc.standard_matched ? '일치' : '일치하는 행 없음'}</Row>
            <Row label="정한 곳">
              {WELDING_SOURCE_LABEL[wc.source] ?? wc.source} <Refs ids={wc.ref_ids} />
            </Row>
          </dl>
        ) : (
          <p className="state">용접 조건을 판별하지 못했어요.</p>
        )}
      </Block>

      <Block letter="b" title="문자/기호 DB" description="1단계에서 읽은 표기를 워크스페이스 사전과 대조해요.">
        {context.dictionary_matches.length === 0 ? (
          <p className="state">대조할 표기가 없어요.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">표기</th>
                  <th scope="col">사전</th>
                  <th scope="col">뜻</th>
                  <th scope="col">대조</th>
                  <th scope="col" className="num">
                    점수
                  </th>
                </tr>
              </thead>
              <tbody>
                {context.dictionary_matches.map((m, i) => (
                  <tr key={`${m.ref_ids.join()}-${i}`}>
                    <td className="code">
                      {m.raw} <Refs ids={m.ref_ids} />
                    </td>
                    <td className="code">{m.code ?? '-'}</td>
                    <td className="cell-title">{m.meaning ?? '-'}</td>
                    <td className={m.match === 'none' ? styles.low : 'secondary'}>{MATCH_LABEL[m.match] ?? m.match}</td>
                    <td className="num">{pct(m.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Block>

      <Block letter="c" title="조립 경로 DB" description="블록에서 부재까지 조립 트리를 따라가 지금 작업의 위치를 찾아요.">
        <dl className="group">
          <Row label="부재">{context.part.node_id ?? '-'}</Row>
          <Row label="조립 경로">
            <span className="mono">{context.part.assembly_path ?? '-'}</span>
          </Row>
          <Row label="단계">{context.part.level ? ASSEMBLY_LEVEL_LABEL[context.part.level] : '-'}</Row>
          <Row label="조립 트리에 있음">
            {context.part.found_in_tree ? '예' : '아니요'} <Refs ids={context.part.ref_ids} />
          </Row>
          {context.part.assembly_path && context.part.ref_ids.length === 0 && (
            <Row label="정한 곳">사진에 부재 표기가 없어 작업에 적은 경로</Row>
          )}
        </dl>
      </Block>

      <Block letter="d" title="VLM 맥락 해석" description="사진과 a·b·c 결과를 함께 보고 표기 전체의 뜻을 해석해요.">
        {context.vlm ? (
          <>
            <p className={styles.quote}>{context.vlm.interpretation}</p>
            <dl className="group">
              <Row label="모델">
                {VLM_PROVIDER_LABEL[context.vlm.provider] ?? context.vlm.provider}, {context.vlm.model}
              </Row>
              <Row label="사진">{context.vlm.image_attached === false ? '사진 없이 1단계 결과만 봄' : '사진을 보고 해석'}</Row>
              <Row label="추론 횟수">{context.vlm.runs}번 (동시에)</Row>
              <Row label="여러 번 추론한 일치도">{pct(context.vlm.consistency)}</Row>
              <Row label="출력 토큰 확률">{pct(context.vlm.token_prob)}</Row>
              <Row label="VLM 이 읽은 표기">
                {[
                  ...context.vlm.reading.texts.map((t) => `${t.ref_id} ${t.text}${t.used ? ' (해석에 씀)' : ''}`),
                  ...context.vlm.reading.symbols.map((s) => `${s.ref_id} ${s.label}${s.used ? ' (해석에 씀)' : ''}`),
                ].join(', ') || '-'}
              </Row>
            </dl>
          </>
        ) : context.vlm_error ? (
          <Notice tone="error" title="VLM 호출이 실패해 VLM 없이 해석했어요">
            {context.vlm_error}
          </Notice>
        ) : (
          <Notice tone={status?.vlm_provider ? 'warning' : 'info'}>{vlmOffReason(status)}</Notice>
        )}
      </Block>

      <Block letter="e" title="셀 형태와 각장" description="PAC 과제 결과 — 셀 좌·우 끝 형태와 수기 각장(F·V·S)을 사전 대조 결과에서 뽑아요.">
        <dl className="group">
          <Row label="셀 형태">
            {context.cell ? (
              <>
                <CellView cell={context.cell} /> <Refs ids={context.cell.ref_ids} />
              </>
            ) : (
              '셀 형태 기호를 찾지 못했어요'
            )}
          </Row>
          <Row label="각장">
            {context.leg_lengths?.length ? <LegLengthList legs={context.leg_lengths} /> : '읽은 각장이 없어요'}
          </Row>
        </dl>
      </Block>

      <section className={styles.block} aria-labelledby="conflicts-title">
        <h2 id="conflicts-title" className={styles.blockTitle}>
          DB 불일치
        </h2>
        <ConflictList conflicts={context.conflicts} />
      </section>
    </>
  )
}

/** 경고·오류는 위에 펼쳐 두고, 참고(info)는 접어 둔다 — 해석은 됐고 확인 항목도 아닌 것 */
function ConflictList({ conflicts }: { conflicts: Conflict[] }) {
  const warnings = conflicts.filter((c) => c.severity !== 'info')
  const notes = conflicts.filter((c) => c.severity === 'info')
  if (conflicts.length === 0) return <p className="state">불일치한 항목이 없어요.</p>
  const item = (c: Conflict, i: number, icon: ReactNode) => (
    <li key={i}>
      {icon}
      <span>
        <strong>{CONFLICT_LABEL[c.type] ?? c.type}</strong> {c.message} <Refs ids={c.ref_ids} />
      </span>
    </li>
  )
  return (
    <>
      {warnings.length === 0 ? (
        <p className="state">확인이 필요한 불일치는 없어요.</p>
      ) : (
        <ul className="check-list check-list--attention">
          {warnings.map((c, i) => item(c, i, <WarningCircle size={18} weight="fill" aria-hidden="true" />))}
        </ul>
      )}
      {notes.length > 0 && (
        <details className={styles.notes}>
          <summary>참고 {notes.length}건 (해석은 됐고 확인 항목은 아니에요)</summary>
          <ul className="check-list">{notes.map((c, i) => item(c, i, <Info size={18} aria-hidden="true" />))}</ul>
        </details>
      )}
    </>
  )
}

function vlmOffReason(status: PipelineStatus | undefined): string {
  if (!status) return 'VLM 해석 결과가 없어요.'
  if (!status.vlm_provider) return 'VLM 을 꺼 두어(.env 의 VLM_PROVIDER) 사전·조립 트리·용접 기준 대조만 했어요.'
  if (!status.vlm_sdk_installed) return `${status.vlm_provider} SDK 가 설치되지 않아 VLM 해석을 건너뛰었어요.`
  if (!status.vlm_api_key_set) return `${status.vlm_provider} API 키가 .env 에 없어 VLM 해석을 건너뛰었어요.`
  return 'VLM 해석 결과가 없어요.'
}

// ── 3단계 신뢰도 산출 ──

const LAYERS: { key: ConfidenceLayer; letter: string; title: string; description: string }[] = [
  { key: 'visual', letter: 'a', title: '시각 인식 신뢰도', description: '글자·기호가 얼마나 또렷하게 읽혔는지' },
  { key: 'db_consistency', letter: 'b', title: 'DB 정합성 신뢰도', description: '사전·조립 트리·용접 기준과 얼마나 맞는지' },
  { key: 'vlm_reasoning', letter: 'c', title: 'VLM 추론 신뢰도', description: 'VLM 해석이 얼마나 일관되고 확실한지' },
]

function ConfidenceStage({ analysis }: { analysis: Analysis }) {
  const report = analysis.confidence
  if (!report) return <p className="state">아직 신뢰도를 산출하지 않았어요.</p>
  const { factors } = report

  const factorRows: Record<ConfidenceLayer, [string, string][]> = {
    visual: [
      ['인식 확률', pct(factors.visual.recognition_prob)],
      ['전처리 보정 강도', pct(factors.visual.correction_strength)],
      ['OCR·VLM 교차 검증 일치도', pct(factors.visual.ocr_vlm_agreement)],
    ],
    db_consistency: [
      ['사전 규칙에 맞는 표기 비율', pct(factors.db_consistency.dictionary_match_rate)],
      ['조립 트리에 부재 있음', factors.db_consistency.part_found == null ? '-' : factors.db_consistency.part_found ? '예' : '아니요'],
      ['용접 기준과 충돌', `${factors.db_consistency.standard_conflicts}건`],
    ],
    vlm_reasoning: [
      ['출력 토큰 확률', pct(factors.vlm_reasoning.token_prob)],
      ['다중 추론 일관성', pct(factors.vlm_reasoning.consistency)],
    ],
  }

  return (
    <>
      <div className={styles.overall}>
        <p className={styles.overallScore}>
          {formatScore(report.overall)}
          <span className="stat-unit">%</span>
        </p>
        <div>
          <p className={styles.overallTitle}>{report.passed ? '기준을 넘었어요' : '확인이 필요해요'}</p>
          <p className={styles.blockDesc}>
            종합 신뢰도는 세 신뢰도 중 가장 낮은 값이고, 기준은 {formatScore(report.threshold)}%예요.
          </p>
        </div>
      </div>

      {LAYERS.map((layer) => (
        <Block key={layer.key} letter={layer.letter} title={layer.title} description={layer.description}>
          <div className={styles.layer}>
            <p className={`${styles.layerScore} ${report[layer.key] < report.threshold ? styles.low : ''}`}>
              {formatScore(report[layer.key])}
              <span className="stat-unit">%</span>
            </p>
            <dl className={`group ${styles.factors}`}>
              {factorRows[layer.key].map(([label, value]) => (
                <Row key={label} label={label}>
                  {value}
                </Row>
              ))}
            </dl>
          </div>
          {report.evidence.some((e) => e.layer === layer.key) && (
            <ul className="check-list">
              {report.evidence
                .filter((e) => e.layer === layer.key)
                .map((e, i) => (
                  <li key={i}>
                    <Check size={16} weight="bold" aria-hidden="true" />
                    <span>
                      {e.message} <Refs ids={e.ref_ids} />
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Block>
      ))}

      <section className={styles.block} aria-labelledby="review-title">
        <h2 id="review-title" className={styles.blockTitle}>
          작업자 확인 항목
        </h2>
        {report.needs_review.length === 0 ? (
          <p className="state">확인할 항목이 없어요.</p>
        ) : (
          <ul className="check-list check-list--attention">
            {report.needs_review.map((item, i) => (
              <li key={i}>
                <WarningCircle size={18} weight="fill" aria-hidden="true" />
                <span>
                  <strong>{REVIEW_REASON_LABEL[item.reason] ?? item.reason}</strong> {item.message}
                  {item.candidates && item.candidates.length > 0 && (
                    <span className={styles.refs}>후보 {item.candidates.join(', ')}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
