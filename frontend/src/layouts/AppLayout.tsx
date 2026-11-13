/**
 * 공통 레이아웃.
 * 상단에 앱 이름 · 가상 기업 기준일(2026-07-01) · 역할 전환, 왼쪽에 메뉴, 가운데에 페이지를 둔다.
 * 시연 패널 메뉴는 시연 관리자에게만 보인다. 메뉴 숨김은 화면 정리일 뿐 보안이 아니다
 * (결재 · 지급 권한은 서버가 403 으로 막는다).
 */
import { NavLink, Outlet } from 'react-router'
import RoleSwitcher from '../components/RoleSwitcher.tsx'
import { useRole } from '../context/RoleContext.tsx'

// 가상 기업 기준일. 6월분 미지급 40건을 처리하는 날이다(설계안 F4).
const BASE_DATE = '2026-07-01'

export default function AppLayout() {
  const { role } = useRole()

  return (
    <div className="app">
      <header className="app-header">
        <strong>W07 판매장려금 통제 데스크</strong>
        <span className="base-date">기준일 {BASE_DATE}</span>
        <RoleSwitcher />
      </header>
      <nav className="app-nav">
        {/* end 가 없으면 모든 주소가 / 로 시작해 처리함이 늘 선택된 것처럼 보인다. */}
        <NavLink to="/" end>
          처리함
        </NavLink>
        <NavLink to="/tasks">작업</NavLink>
        <NavLink to="/master-changes">정정 신고</NavLink>
        <NavLink to="/events">이벤트 이력</NavLink>
        <NavLink to="/ai-log">AI 기록</NavLink>
        {role === '시연 관리자' && <NavLink to="/demo">시연 패널</NavLink>}
      </nav>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
