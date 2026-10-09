import { BackendStatus } from './components/BackendStatus'

function App() {
  return (
    <main className="app">
      <header>
        <h1>Vision Welding AI</h1>
        <p className="lead">
          현장에서 촬영한 선박 블록 부재 마킹을 인식해 용접 작업 정보를 분석하고,
          결과를 로봇용 JSON으로 내보내는 AI 기반 용접 작업 분석 서비스입니다.
        </p>
      </header>
      <BackendStatus />
    </main>
  )
}

export default App
