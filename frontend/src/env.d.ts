interface ImportMetaEnv {
  /** API 기본 경로. 미설정 시 '/api' (개발 서버 프록시 사용) */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
