/**
 * 현재 역할 컨텍스트.
 * 역할 5개(영업지원팀 · 영업임원 · 재무 · 내부감사 · 시연 관리자)마다
 * 이름 · 첫 화면 · 처리함 · 작업 기본 필터를 정해 두고,
 * 지금 역할을 보관 · 전환한다. 고른 역할은 브라우저에 저장해 새로고침해도 유지한다.
 * 역할 · 이름은 각 화면이 결정 · 지급 요청 본문에 넣는다(09). 서버 권한 검사를 대신하지 않는다.
 */
import { createContext, useContext, useState, type ReactNode } from 'react'
import { ClaimStatus, Department } from '../types/enums.ts'

// 이름은 백엔드 테스트(09 · 11)와 같게 맞춰, 이력의 처리자 이름이 늘 같게 보이게 한다.
// inbox 는 처리함이 처음 보여 줄 상태(빈 배열 = 전체). 결정 권한이 아니다(서버 403 · 409 가 막는다).
// dept 는 작업 화면이 처음 보여 줄 부서(null = 전체). 역할 이름으로 찾지 않고 표에 적는다.
export const ROLE_PROFILES = [
  {
    role: '영업지원팀',
    actor: '김지원',
    home: '/',
    inbox: [ClaimStatus.AWAITING_SUPPORT],
    dept: Department.SALES_SUPPORT,
  },
  {
    role: '영업임원',
    actor: '박임원',
    home: '/',
    inbox: [ClaimStatus.AWAITING_EXECUTIVE],
    dept: null,
  },
  {
    role: '재무',
    actor: '이재무',
    home: '/',
    inbox: [ClaimStatus.APPROVED, ClaimStatus.PAYMENT_ORDERED],
    dept: Department.FINANCE,
  },
  { role: '내부감사', actor: '최감사', home: '/tasks', inbox: [], dept: Department.AUDIT },
  { role: '시연 관리자', actor: '시연관리자', home: '/demo', inbox: [], dept: null },
] as const

export type RoleProfile = (typeof ROLE_PROFILES)[number]
export type ActorRole = RoleProfile['role']

const STORAGE_KEY = 'w07.role'
const DEFAULT_PROFILE = ROLE_PROFILES[0]

/** 문자열이 역할 5개 중 하나인지 확인해 그 역할의 정보를 돌려준다. */
export function findProfile(role: string | null): RoleProfile | undefined {
  return ROLE_PROFILES.find((profile) => profile.role === role)
}

/** 브라우저에 저장된 역할. 저장소가 막힌 브라우저(사생활 보호 모드 등)에서도 기본 역할로 돈다. */
function loadProfile(): RoleProfile {
  try {
    return findProfile(localStorage.getItem(STORAGE_KEY)) ?? DEFAULT_PROFILE
  } catch {
    return DEFAULT_PROFILE
  }
}

type RoleContextValue = {
  role: ActorRole
  actor: string
  inbox: readonly ClaimStatus[]
  dept: Department | null
  setRole: (role: ActorRole) => void
}

const RoleContext = createContext<RoleContextValue | null>(null)

export function RoleProvider({ children }: { children: ReactNode }) {
  // 이름은 역할에서 꺼낸다. 따로 상태로 두면 서로 어긋날 수 있다.
  const [profile, setProfile] = useState<RoleProfile>(loadProfile)

  function setRole(role: ActorRole) {
    const next = findProfile(role) ?? DEFAULT_PROFILE
    setProfile(next)
    try {
      localStorage.setItem(STORAGE_KEY, next.role)
    } catch {
      // 저장하지 못해도 이번 화면에서는 바뀐 역할로 동작한다.
    }
  }

  // React 19 부터 Context 자체를 Provider 로 쓴다(.Provider 불필요).
  return (
    <RoleContext
      value={{
        role: profile.role,
        actor: profile.actor,
        inbox: profile.inbox,
        dept: profile.dept,
        setRole,
      }}
    >
      {children}
    </RoleContext>
  )
}

/** 지금 역할 · 이름 · 처리함 · 작업 기본 필터와 역할 전환 함수. RoleProvider 안에서만 쓸 수 있다. */
export function useRole(): RoleContextValue {
  const value = useContext(RoleContext)
  if (value === null) {
    throw new Error('useRole 은 RoleProvider 안에서만 쓸 수 있습니다')
  }
  return value
}
