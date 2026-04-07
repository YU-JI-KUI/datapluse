import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Loader2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { authApi } from '@/lib/api'

export default function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!username || !password) return toast.error('请填写用户名和密码')
    setLoading(true)
    try {
      const res = await authApi.login(username, password)
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('username', res.data.username)
      navigate('/dashboard')
    } catch (err) {
      toast.error(err.response?.data?.detail || '登录失败，请检查用户名密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 items-center justify-center text-white font-bold text-2xl mb-4">
            D
          </div>
          <h1 className="text-2xl font-bold text-white">Datapluse</h1>
          <p className="text-gray-400 text-sm mt-1">AI 数据飞轮平台</p>
        </div>

        {/* Form */}
        <div className="bg-white/5 backdrop-blur border border-white/10 rounded-2xl p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">用户名</label>
              <Input
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="admin"
                className="bg-white/10 border-white/20 text-white placeholder:text-gray-500"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">密码</label>
              <Input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="bg-white/10 border-white/20 text-white placeholder:text-gray-500"
              />
            </div>
            <Button type="submit" className="w-full mt-2" disabled={loading}>
              {loading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 登录中...</> : <><Lock className="w-4 h-4 mr-2" /> 登录</>}
            </Button>
          </form>
          <p className="text-center text-xs text-gray-500 mt-4">
            默认账号: admin / datapluse2024
          </p>
        </div>
      </div>
    </div>
  )
}
