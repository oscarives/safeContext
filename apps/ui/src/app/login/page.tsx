'use client'

export default function LoginPage() {
  const handleLogin = () => {
    const keycloakUrl = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? 'http://localhost:8080'
    const realm = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'safecontext'
    const clientId = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'safecontext-ui'
    const redirectUri = encodeURIComponent(`${window.location.origin}/auth/callback`)

    window.location.href = `${keycloakUrl}/realms/${realm}/protocol/openid-connect/auth` +
      `?client_id=${clientId}` +
      `&redirect_uri=${redirectUri}` +
      `&response_type=code` +
      `&scope=openid profile email` +
      `&kc_action=CONFIGURE_TOTP`  // force MFA setup on first login
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white p-8 rounded-xl shadow-md w-full max-w-sm">
        <h1 className="text-2xl font-bold text-brand mb-2">SafeContext</h1>
        <p className="text-gray-500 text-sm mb-6">
          Enterprise document governance platform
        </p>
        <button
          onClick={handleLogin}
          className="w-full py-2.5 bg-brand text-white rounded-lg font-medium hover:bg-brand-light transition-colors"
        >
          Sign in with SSO
        </button>
        <p className="text-xs text-gray-400 mt-4 text-center">
          MFA is required for all accounts
        </p>
      </div>
    </main>
  )
}
