import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Shield, ChevronDown, ChevronRight, Save, Lock } from 'lucide-react'
import { roleApi } from '@/lib/api'
import { Button } from '@/components/ui/button'

const ROLE_STYLE = {
  admin:     'bg-red-100 text-red-700',
  annotator: 'bg-blue-100 text-blue-700',
  evaluator: 'bg-green-100 text-green-700',
  viewer:    'bg-gray-100 text-gray-600',
}

export default function RolePermissions() {
  // 权限全集（按模块分组）+ 各角色当前权限
  const { data: permData }  = useQuery({ queryKey: ['permissions'], queryFn: () => roleApi.listPermissions() })
  const { data: roleData }  = useQuery({ queryKey: ['roles-full'],  queryFn: () => roleApi.listRoles() })

  const groups = permData?.data?.data || []            // [{ module, permissions:[{code,label}] }]
  const roles  = roleData?.data?.data || []            // [{ name, description, permissions:[...] }]

  const [activeRole, setActiveRole] = useState(null)
  const [checked, setChecked]       = useState(new Set())
  const [collapsed, setCollapsed]   = useState(new Set())
  const [saving, setSaving]         = useState(false)

  // 首次加载/切换角色时，把该角色的当前权限灌进勾选集
  const current = roles.find(r => r.name === activeRole)
  const isAdmin = activeRole === 'admin'

  useEffect(() => {
    if (!activeRole && roles.length) setActiveRole(roles[0].name)
  }, [roles, activeRole])

  useEffect(() => {
    if (current) setChecked(new Set(current.permissions || []))
  }, [activeRole, roleData])   // 切角色或数据刷新时重置

  const allCodes = useMemo(() => groups.flatMap(g => g.permissions.map(p => p.code)), [groups])

  function toggle(code) {
    if (isAdmin) return
    setChecked(prev => {
      const next = new Set(prev)
      next.has(code) ? next.delete(code) : next.add(code)
      return next
    })
  }

  // 模块级全选/取消：父节点点击
  function toggleModule(group) {
    if (isAdmin) return
    const codes = group.permissions.map(p => p.code)
    const allOn = codes.every(c => checked.has(c))
    setChecked(prev => {
      const next = new Set(prev)
      codes.forEach(c => allOn ? next.delete(c) : next.add(c))
      return next
    })
  }

  function moduleState(group) {
    const codes = group.permissions.map(p => p.code)
    const on = codes.filter(c => checked.has(c)).length
    if (on === 0) return 'none'
    if (on === codes.length) return 'all'
    return 'some'
  }

  function toggleCollapse(module) {
    setCollapsed(prev => {
      const next = new Set(prev)
      next.has(module) ? next.delete(module) : next.add(module)
      return next
    })
  }

  async function handleSave() {
    if (isAdmin) return
    setSaving(true)
    try {
      await roleApi.updatePermissions(activeRole, allCodes.filter(c => checked.has(c)))
      toast.success('权限已更新，相关用户重新登录后生效')
    } catch (err) {
      toast.error(err.response?.data?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const dirty = current && (
    checked.size !== (current.permissions || []).length ||
    [...checked].some(c => !(current.permissions || []).includes(c))
  )

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center gap-2 mb-1">
        <Shield className="w-5 h-5 text-blue-500" />
        <h1 className="text-xl font-semibold">角色权限管理</h1>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        勾选每个角色可访问的权限。修改后需相关用户<strong>重新登录</strong>才会生效。
      </p>

      {/* 角色 tab */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {roles.map(r => (
          <button
            key={r.name}
            onClick={() => setActiveRole(r.name)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
              activeRole === r.name
                ? 'border-blue-400 bg-blue-50 text-blue-700'
                : 'border-transparent hover:bg-gray-50 text-gray-600'
            }`}
          >
            <span className={`inline-block px-1.5 py-0.5 rounded text-xs mr-1.5 ${ROLE_STYLE[r.name] || 'bg-gray-100 text-gray-600'}`}>
              {r.name}
            </span>
          </button>
        ))}
      </div>

      {isAdmin && (
        <div className="flex items-center gap-2 mb-4 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-700">
          <Lock className="w-4 h-4" />
          admin 角色拥有全部权限（<code>*</code>），不可修改。
        </div>
      )}

      {/* 权限树 */}
      <div className="border rounded-lg divide-y">
        {groups.map(group => {
          const state    = moduleState(group)
          const isOpen   = !collapsed.has(group.module)
          return (
            <div key={group.module}>
              <div className="flex items-center gap-2 px-3 py-2 bg-gray-50">
                <button onClick={() => toggleCollapse(group.module)} className="text-gray-400 hover:text-gray-600">
                  {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
                <input
                  type="checkbox"
                  checked={state === 'all'}
                  ref={el => { if (el) el.indeterminate = state === 'some' }}
                  onChange={() => toggleModule(group)}
                  disabled={isAdmin}
                />
                <span className="font-medium text-sm">{group.module}</span>
                <span className="text-xs text-gray-400">
                  {group.permissions.filter(p => checked.has(p.code)).length}/{group.permissions.length}
                </span>
              </div>
              {isOpen && (
                <div className="pl-10 pr-3 py-1.5 space-y-1">
                  {group.permissions.map(p => (
                    <label key={p.code} className={`flex items-center gap-2 py-1 rounded px-1.5 ${isAdmin ? 'opacity-60' : 'cursor-pointer hover:bg-gray-50'}`}>
                      <input
                        type="checkbox"
                        checked={isAdmin || checked.has(p.code)}
                        onChange={() => toggle(p.code)}
                        disabled={isAdmin}
                      />
                      <span className="text-sm">{p.label}</span>
                      <code className="text-xs text-gray-400">{p.code}</code>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {!isAdmin && (
        <div className="flex items-center gap-3 mt-5">
          <Button onClick={handleSave} disabled={saving || !dirty}>
            <Save className="w-4 h-4 mr-1.5" />
            {saving ? '保存中…' : '保存权限'}
          </Button>
          {dirty && <span className="text-sm text-amber-600">有未保存的更改</span>}
        </div>
      )}
    </div>
  )
}
