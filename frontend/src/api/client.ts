/**
 * API 호출 공통 모듈.
 * /api 앞부분, JSON 변환, 오류 응답을 ApiError 로 바꾸는 일을 맡는다.
 * 결정자 이름 · 역할은 헤더가 아니라 각 화면이 요청 본문에 넣는다(09 결정).
 */

/** 서버가 2xx 가 아닌 응답을 돌려줬을 때. message 는 서버가 보낸 문장이다. */
export class ApiError extends Error {
  // erasableSyntaxOnly 라 constructor(readonly status) 줄임 문법을 쓸 수 없다.
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 서버 오류 본문에서 사람이 읽을 문장을 꺼낸다. 403 · 404 · 409 는 문자열, 422 는 배열이다. */
function errorMessage(data: unknown, status: number): string {
  if (typeof data === 'object' && data !== null && 'detail' in data) {
    const { detail } = data
    if (typeof detail === 'string') {
      return detail
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item: unknown) =>
          typeof item === 'object' && item !== null && 'msg' in item
            ? // Pydantic 이 직접 만든 검사 오류(model_validator)에는 "Value error, " 가 앞에 붙는다.
              String(item.msg).replace(/^Value error, /, '')
            : String(item),
        )
        .join(' / ')
    }
  }
  return `요청 실패 (${status})`
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  // fetch 는 네트워크가 끊겼을 때만 예외를 던진다. 409 도 '도착한 응답'이라 상태 코드를 직접 본다.
  if (!res.ok) {
    // 서버가 죽어 프록시가 HTML 을 돌려주면 JSON 이 아니다.
    const data: unknown = await res.json().catch(() => null)
    throw new ApiError(res.status, errorMessage(data, res.status))
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
}
