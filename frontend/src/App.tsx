/**
 * 최상위 화면: 주소 → 페이지 연결(react-router 선언형 방식).
 * 화면 주소(/claims/RB-00006 등)는 React 가 고르고, 백엔드 main.py 는 없는 주소에 index.html 을 돌려준다.
 * NotReady 는 없는 주소(*)에만 쓴다.
 */
import { BrowserRouter, Route, Routes } from 'react-router'
import { RoleProvider } from './context/RoleContext.tsx'
import AppLayout from './layouts/AppLayout.tsx'
import AIRecommendationLogPage from './pages/AIRecommendationLogPage.tsx'
import ClaimDetailPage from './pages/ClaimDetailPage.tsx'
import DemoPanelPage from './pages/DemoPanelPage.tsx'
import EventLogPage from './pages/EventLogPage.tsx'
import InboxPage from './pages/InboxPage.tsx'
import MasterChangePage from './pages/MasterChangePage.tsx'
import TasksPage from './pages/TasksPage.tsx'

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
            <Route index element={<InboxPage />} />
            <Route path="claims/:rebateId" element={<ClaimDetailPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="master-changes" element={<MasterChangePage />} />
            <Route path="events" element={<EventLogPage />} />
            <Route path="ai-log" element={<AIRecommendationLogPage />} />
            <Route path="demo" element={<DemoPanelPage />} />
            <Route path="*" element={<NotReady title="없는 화면" roadmap="-" />} />
          </Route>
        </Routes>
      </RoleProvider>
    </BrowserRouter>
  )
}
