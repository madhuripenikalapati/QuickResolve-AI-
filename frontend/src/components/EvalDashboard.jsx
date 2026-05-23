import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { runEval, getEvalResults } from '../api'
import { Play, RefreshCw } from 'lucide-react'

const COLORS = { pass: '#22c55e', partial: '#f59e0b', fail: '#ef4444' }
const PIE_COLORS = ['#22c55e', '#ef4444']

export default function EvalDashboard() {
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleRun() {
    setLoading(true)
    setError(null)
    try {
      const data = await runEval()
      setResults(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleLoad() {
    setLoading(true)
    setError(null)
    try {
      const data = await getEvalResults()
      if (data.error) setError(data.error)
      else setResults(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const workflowData = results
    ? Object.entries(results.by_workflow || {}).map(([name, counts]) => ({
        name,
        pass: counts.pass,
        partial: counts.partial,
        fail: counts.fail,
      }))
    : []

  const hallucData = results
    ? [
        { name: 'Clean', value: results.tool_hallucination?.clean || 0 },
        { name: 'Hallucinated', value: results.tool_hallucination?.hallucinated || 0 },
      ]
    : []

  const gracefulData = results
    ? [
        { name: 'Graceful', value: results.graceful_failure?.graceful || 0 },
        { name: 'Crashed', value: results.graceful_failure?.crashed || 0 },
      ]
    : []

  return (
    <div className="p-3 space-y-4">
      <div className="flex gap-2">
        <button
          onClick={handleRun}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          <Play size={11} />
          Run Eval
        </button>
        <button
          onClick={handleLoad}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded-lg hover:bg-slate-200 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Load Latest
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}
      {loading && <p className="text-xs text-slate-400">Running eval suite... (~60 API calls)</p>}

      {results && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-2">
            {[
              {
                label: 'Task Completion',
                value: `${((results.task_completion.pass / results.total) * 100).toFixed(0)}%`,
                sub: `${results.task_completion.pass}/${results.total} pass`,
                color: 'text-green-600',
              },
              {
                label: 'Tool Cleanliness',
                value: `${((results.tool_hallucination.clean / results.total) * 100).toFixed(0)}%`,
                sub: `${results.tool_hallucination.clean} clean`,
                color: 'text-blue-600',
              },
              {
                label: 'Valid Tool Use',
                value: `${((results.invalid_tool_use.valid / results.total) * 100).toFixed(0)}%`,
                sub: `${results.invalid_tool_use.valid} valid`,
                color: 'text-purple-600',
              },
              {
                label: 'Graceful Failures',
                value: (() => {
                  const total = (results.graceful_failure.graceful || 0) + (results.graceful_failure.crashed || 0)
                  return total > 0 ? `${((results.graceful_failure.graceful / total) * 100).toFixed(0)}%` : 'N/A'
                })(),
                sub: `${results.graceful_failure.graceful || 0} graceful`,
                color: 'text-orange-600',
              },
            ].map(card => (
              <div key={card.label} className="bg-white rounded-lg p-2.5 border border-slate-100">
                <p className="text-[10px] text-slate-400">{card.label}</p>
                <p className={`text-lg font-semibold ${card.color}`}>{card.value}</p>
                <p className="text-[10px] text-slate-400">{card.sub}</p>
              </div>
            ))}
          </div>

          {/* Task completion by workflow */}
          {workflowData.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Task Completion by Workflow</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={workflowData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} />
                  <YAxis tick={{ fontSize: 9 }} />
                  <Tooltip contentStyle={{ fontSize: 11 }} />
                  <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="pass" stackId="a" fill={COLORS.pass} />
                  <Bar dataKey="partial" stackId="a" fill={COLORS.partial} />
                  <Bar dataKey="fail" stackId="a" fill={COLORS.fail} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Hallucination + Graceful side by side */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { title: 'Hallucination', data: hallucData },
              { title: 'Graceful Failure', data: gracefulData },
            ].map(({ title, data }) => (
              <div key={title}>
                <p className="text-xs font-medium text-slate-500 mb-1">{title}</p>
                <ResponsiveContainer width="100%" height={100}>
                  <PieChart>
                    <Pie data={data} cx="50%" cy="50%" innerRadius={25} outerRadius={40} dataKey="value" label={({ name, value }) => `${name}: ${value}`} labelLine={false} fontSize={9}>
                      {data.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ fontSize: 10 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>

          {/* Details table */}
          <div>
            <p className="text-xs font-medium text-slate-500 mb-1">Test Details</p>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="text-left p-1.5 text-slate-400 font-medium">ID</th>
                    <th className="text-left p-1.5 text-slate-400 font-medium">Task</th>
                    <th className="text-left p-1.5 text-slate-400 font-medium">Halluc</th>
                    <th className="text-left p-1.5 text-slate-400 font-medium">Tools</th>
                  </tr>
                </thead>
                <tbody>
                  {results.details.map(d => (
                    <tr key={d.test_id} className="border-t border-slate-50 hover:bg-slate-50">
                      <td className="p-1.5 font-mono text-slate-600">{d.test_id}</td>
                      <td className="p-1.5">
                        <span className={`px-1.5 py-0.5 rounded-full font-medium ${
                          d.scores.task_completion === 'pass' ? 'bg-green-100 text-green-700' :
                          d.scores.task_completion === 'partial' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-red-100 text-red-700'
                        }`}>
                          {d.scores.task_completion}
                        </span>
                      </td>
                      <td className="p-1.5">
                        <span className={`px-1.5 py-0.5 rounded-full ${
                          d.scores.tool_hallucination === 'clean' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {d.scores.tool_hallucination}
                        </span>
                      </td>
                      <td className="p-1.5">
                        <span className={`px-1.5 py-0.5 rounded-full ${
                          d.scores.tool_validity === 'valid' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {d.scores.tool_validity}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
