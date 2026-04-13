import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import {
  Database, CheckCircle, AlertTriangle, Cpu,
  ArrowRight, Play, RefreshCw, Tag,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { dataApi, pipelineApi, getCurrentDatasetId } from '@/lib/api'
import { toast } from 'sonner'
import { useState, useEffect } from 'react'

const STATUS_CONFIG = [
  { key: 'raw',           label: '原始',    color: '#6b7280' },
  { key: 'cleaned',       label: '已清洗',  color: '#3b82f6' },
  { key: 'pre_annotated', label: '预标注',  color: '#8b5cf6' },
  { key: 'annotated',     label: '已标注',  color: '#f97316' },
  { key: 'checked',       label: '已检测',  color: '#22c55e' },
]

function StatCard({ title, value, icon: Icon, color, sub }) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold mt-1">{value ?? '-'}</p>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
          </div>
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
            <Icon className="w-6 h-6 text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [runningPipeline, setRunningPipeline] = useState(false)
  const [datasetId, setDatasetId] = useState(() => getCurrentDatasetId())

  // 切换数据集时重新加载 + 初始加载
  useEffect(() => {
    const handler = (e) => setDatasetId(e.detail.datasetId)
    window.addEventListener('datasetChanged', handler)
    
    // 如果初始没有datasetId，等待Layout设置
    if (datasetId === null) {
      const checkDataset = () => {
        const current = getCurrentDatasetId()
        if (current !== null) {
          setDatasetId(current)
        } else {
          // 继续检查
          setTimeout(checkDataset, 100)
        }
      }
      checkDataset()
    }
    
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  const { data: statsRes, refetch: refetchStats } = useQuery({
    queryKey: ['stats', datasetId],
    queryFn: () => dataApi.stats(datasetId),
    refetchInterval: 10000,
    enabled: datasetId !== null,
  })

  const { data: pipelineRes, refetch: refetchPipeline } = useQuery({
    queryKey: ['pipeline-status', datasetId],
    queryFn: () => pipelineApi.status(datasetId),
    refetchInterval: 10000,
    enabled: datasetId !== null,
  })

  const stats = statsRes?.data?.data || {}
  const pipeline = pipelineRes?.data?.data || {}

  const chartData = STATUS_CONFIG.map(s => ({
    name: s.label,
    count: stats[s.key] || 0,
    color: s.color,
  }))

  async function handleRunPipeline() {
    setRunningPipeline(true)
    try {
      await pipelineApi.run(datasetId)
      toast.success('Pipeline 已启动')
      refetchPipeline()
    } catch (err) {
      toast.error(err.response?.data?.detail || '启动失败')
    } finally {
      setRunningPipeline(false)
    }
  }

  const pipelineStatusColor = {
    idle: 'secondary',
    running: 'info',
    completed: 'success',
    error: 'destructive',
  }[pipeline.status] || 'secondary'

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">数据飞轮全局概览</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { refetchStats(); refetchPipeline() }}>
            <RefreshCw className="w-4 h-4 mr-2" /> 刷新
          </Button>
          <Button size="sm" onClick={handleRunPipeline} disabled={runningPipeline || pipeline.status === 'running'}>
            <Play className="w-4 h-4 mr-2" />
            {pipeline.status === 'running' ? '运行中...' : '运行 Pipeline'}
          </Button>
        </div>
      </div>

      {/* Pipeline 状态条 */}
      {pipeline.status === 'running' && (
        <Card className="border-blue-200 bg-blue-50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                <span className="text-sm font-medium text-blue-700">
                  Pipeline 运行中 — {pipeline.current_step}
                </span>
              </div>
              <span className="text-sm text-blue-600">{pipeline.progress}%</span>
            </div>
            <Progress value={pipeline.progress} className="h-1.5" />
          </CardContent>
        </Card>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="总数据量" value={stats.total} icon={Database} color="bg-gray-700" />
        <StatCard title="待标注" value={stats.pre_annotated} icon={Cpu} color="bg-violet-500" sub="预标注完成" />
        <StatCard title="已标注" value={stats.annotated} icon={Tag} color="bg-orange-500" sub="人工标注" />
        <StatCard title="高质量数据" value={stats.checked} icon={CheckCircle} color="bg-green-500" sub="通过冲突检测" />
      </div>

      {/* Chart + Pipeline status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Bar chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">各阶段数据分布</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} barSize={40}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => [v, '数量']} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Pipeline 状态面板 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              Pipeline 状态
              <Badge variant={pipelineStatusColor}>
                {pipeline.status || 'idle'}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {pipeline.error && (
              <div className="text-xs text-red-500 bg-red-50 rounded p-2">
                错误: {pipeline.error}
              </div>
            )}
            <div className="text-xs text-muted-foreground space-y-1">
              {pipeline.started_at && <div>开始: {new Date(pipeline.started_at).toLocaleString('zh-CN')}</div>}
              {pipeline.finished_at && <div>完成: {new Date(pipeline.finished_at).toLocaleString('zh-CN')}</div>}
              {pipeline.current_step && <div>步骤: {pipeline.current_step}</div>}
            </div>

            <div className="pt-2 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">快速操作</p>
              <button onClick={() => navigate('/data')} className="flex items-center justify-between w-full text-sm px-3 py-2 rounded-lg hover:bg-accent transition-colors">
                <span className="flex items-center gap-2"><Database className="w-4 h-4" />上传数据</span>
                <ArrowRight className="w-3 h-3 opacity-40" />
              </button>
              <button onClick={() => navigate('/annotation')} className="flex items-center justify-between w-full text-sm px-3 py-2 rounded-lg hover:bg-accent transition-colors">
                <span className="flex items-center gap-2"><Tag className="w-4 h-4" />开始标注</span>
                <ArrowRight className="w-3 h-3 opacity-40" />
              </button>
              <button onClick={() => navigate('/conflicts')} className="flex items-center justify-between w-full text-sm px-3 py-2 rounded-lg hover:bg-accent transition-colors">
                <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />冲突检测</span>
                <ArrowRight className="w-3 h-3 opacity-40" />
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
