/**
 * 역할 전환 선택 상자. 역할을 바꾸면 그 역할의 첫 화면으로 이동한다.
 */
import { useNavigate } from 'react-router'
import { ROLE_PROFILES, findProfile, useRole } from '../context/RoleContext.tsx'

export default function RoleSwitcher() {
  const { role, setRole } = useRole()
  const navigate = useNavigate()

  return (
    <label className="role-switcher">
      역할
      <select
        value={role}
        onChange={(event) => {
          // 선택 값은 string 이다. 역할 표에서 찾아 확인한 뒤에 쓴다(as 로 억지 변환하지 않음).
          const profile = findProfile(event.target.value)
          if (profile === undefined) return
          setRole(profile.role)
          navigate(profile.home)
        }}
      >
        {ROLE_PROFILES.map((profile) => (
          <option key={profile.role} value={profile.role}>
            {profile.role} · {profile.actor}
          </option>
        ))}
      </select>
    </label>
  )
}
