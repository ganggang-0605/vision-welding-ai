import { SignOut, UserCirclePlus } from '@phosphor-icons/react'
import { Link, useNavigate } from 'react-router'
import { getPipelineStatus } from '../api/pipeline'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { signOut, useAccounts } from '../lib/accounts'
import { formatDateTime } from '../lib/format'
import { VLM_PROVIDER_LABEL } from '../lib/labels'
import { paths } from '../lib/paths'
import { TEXT_SIZE_OPTIONS, THEME_OPTIONS, useTextSize, useThemePreference } from '../lib/preferences'
import styles from './PreferencesPage.module.css'

/**
 * 설정 > 내 설정 > 환경설정: 계정, 화면 모드, 글씨 크기.
 * 워크스페이스와 상관없이 모든 화면에 똑같이 적용되고, 이 브라우저에만 저장된다.
 */
export function PreferencesPage() {
  const { me } = useWorkspaceContext()
  const { activeId } = useAccounts()
  const navigate = useNavigate()
  const [theme, setTheme] = useThemePreference()
  const [textSize, setTextSize] = useTextSize()
  const pipeline = useAsync((signal) => getPipelineStatus(signal), [])

  const signOutHere = () => {
    if (!activeId) return
    signOut(activeId)
    // 남은 계정의 마지막 워크스페이스로 (없으면 계정 고르기).
    navigate('/')
  }

  return (
    <>
      <PageHeader
        title="환경설정"
        description="모든 워크스페이스에 똑같이 적용되고, 이 브라우저에만 저장돼요."
      />

      <section aria-labelledby="account-title">
        <h2 id="account-title" className="section-title">
          계정
        </h2>
        <div className={`group ${styles.account}`}>
          <span className={styles.avatar} aria-hidden="true">
            {me?.name.charAt(0)}
          </span>
          <span className={styles.accountText}>
            <span>{me?.name ?? '불러오는 중'}</span>
            <span className={styles.email}>{me?.email}</span>
          </span>
          <span className="button-row">
            <Link className="btn btn--small" to={paths.login('add')}>
              <UserCirclePlus size={15} aria-hidden="true" />
              계정 추가
            </Link>
            <button type="button" className="btn btn--small" onClick={signOutHere}>
              <SignOut size={15} aria-hidden="true" />
              로그아웃
            </button>
          </span>
        </div>
      </section>

      <section className="section" aria-labelledby="theme-title">
        <h2 id="theme-title" className="section-title">
          화면 모드
        </h2>
        <div className="segmented" role="group" aria-labelledby="theme-title">
          {THEME_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={theme === option.value}
              onClick={() => setTheme(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="field-hint">
          {theme === 'system' ? '맥·휴대폰의 라이트/다크 설정을 따라가요.' : '시스템 설정과 상관없이 고정돼요.'}
        </p>
      </section>

      <section className="section" aria-labelledby="text-size-title">
        <h2 id="text-size-title" className="section-title">
          글씨 크기
        </h2>
        <div className="segmented" role="group" aria-labelledby="text-size-title">
          {TEXT_SIZE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={textSize === option.value}
              onClick={() => setTextSize(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="field-hint">현장 태블릿처럼 멀리서 볼 때는 크게를 써 보세요.</p>
      </section>

      <section className="section" aria-labelledby="pipeline-title">
        <h2 id="pipeline-title" className="section-title">
          AI 모델 연결
        </h2>
        <p className="section-desc">서버의 .env 와 설치된 패키지 기준이에요. 바꾸면 백엔드를 다시 켜야 반영돼요.</p>
        {pipeline.data && (
          <dl className="group">
            <div className="group-row">
              <dt>1단계 문자 인식 (OCR)</dt>
              <dd>{pipeline.data.ocr_available ? Object.values(pipeline.data.ocr_models).join(', ') : '설치 안 됨'}</dd>
            </div>
            <div className="group-row">
              <dt>1단계 기호 인식 (YOLO)</dt>
              <dd>{pipeline.data.symbol_detector_available ? '연결됨' : '연결 전'}</dd>
            </div>
            <div className="group-row">
              <dt>2단계 VLM</dt>
              <dd>
                {pipeline.data.vlm_provider
                  ? `${VLM_PROVIDER_LABEL[pipeline.data.vlm_provider] ?? pipeline.data.vlm_provider}, ${pipeline.data.vlm_model}, ${pipeline.data.vlm_runs}번 추론`
                  : '꺼짐'}
              </dd>
            </div>
            {pipeline.data.vlm_provider && (
              <div className="group-row">
                <dt>VLM API 키·SDK</dt>
                <dd>
                  {pipeline.data.vlm_api_key_set ? '키 있음' : '키 없음'}, {pipeline.data.vlm_sdk_installed ? 'SDK 설치됨' : 'SDK 설치 안 됨'}
                </dd>
              </div>
            )}
            {pipeline.data.vlm_last_error && (
              <div className="group-row">
                <dt>최근 VLM 호출 실패</dt>
                <dd className={styles.error}>
                  {pipeline.data.vlm_last_error}
                  {pipeline.data.vlm_last_error_at && (
                    <span className="secondary"> ({formatDateTime(pipeline.data.vlm_last_error_at)})</span>
                  )}
                </dd>
              </div>
            )}
            <div className="group-row">
              <dt>3단계 통과 기준</dt>
              <dd>{pipeline.data.confidence_threshold}%</dd>
            </div>
          </dl>
        )}
      </section>
    </>
  )
}
