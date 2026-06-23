/** 首页「立即体验」：SaaS 走邮箱登录，Private 走固定 user_id="private" 的 SSO 登录 */
export async function startExperience(router) {
  let deployMode = 'saas'
  try {
    const cfg = await fetch('/api/app-config').then(r => r.json())
    deployMode = cfg.deployment_mode || 'saas'
  } catch {
    /* 网络异常降级为 saas */
  }

  if (deployMode !== 'private') {
    router.push('/register')
    return
  }

  try {
    const res = await fetch('/api/user/private-user').then(r => r.json())
    if (res.success) {
      const loginRes = await fetch('/api/user/sso-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ user_id: 'private' }),
      })
      const loginData = await loginRes.json()
      if (loginData.success) {
        window.location.href = '/chat'
      } else {
        router.push('/setup')
      }
    } else {
      router.push('/setup')
    }
  } catch {
    router.push('/setup')
  }
}
