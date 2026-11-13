/**
 * 최상위 화면: 주소 → 페이지 연결(react-router 선언형 방식).
 * 화면 주소(/claims/RB-00006 등)는 React 가 고르고, 백엔드 main.py 는 없는 주소에 index.html 을 돌려준다.
 * 처리함 · 작업 · 이벤트 이력은 13 · 15 에서 실제 페이지로 바꾼다. 그때 NotReady 를 지운다.
 */
import { BrowserRouter, Route, Routes } from 'react-router'
import { RoleProvider } from './context/RoleContext.tsx'
import AppLayout from './layouts/AppLayout.tsx'
import DemoPanelPage from './pages/DemoPanelPage.tsx'

/** 아직 만들지 않은 화면 자리. */
function NotReady({ title, roadmap }: { title: string; roadmap: string }) {
  return (
    <section>
      <h2>{title}</h2>
      <p>준비 중입니다(로드맵 {roadmap}).</p>
    </section>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <RoleProvider>
        <Routes>
          {/* 레이아웃 경로: 주소에는 아무것도 붙지 않고, 자식 페이지가 Outlet 자리에 들어간다. */}
          <Route element={<AppLayout />}>
            <Route index element={<NotReady title="처리함" roadmap="13" />} />
            <Route path="tasks" element={<NotReady title="작업 목록" roadmap="15" />} />
            <Route path="events" element={<NotReady title="이벤트 이력" roadmap="15" />} />
            <Route path="demo" element={<DemoPanelPage />} />
            <Route path="*" element={<NotReady title="없는 화면" roadmap="-" />} />
          </Route>
        </Routes>
      </RoleProvider>
    </BrowserRouter>
  )
}
