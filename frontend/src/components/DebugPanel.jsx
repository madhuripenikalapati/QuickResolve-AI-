import { useState } from 'react'
import ToolCallTrace from './ToolCallTrace'
import SessionMemory from './SessionMemory'
import EvalDashboard from './EvalDashboard'

const TABS = ['Tool Trace', 'Memory', 'Eval']

export default function DebugPanel({ toolCalls, sessionState }) {
  const [activeTab, setActiveTab] = useState('Tool Trace')

  return (
    <div className="flex flex-col h-full bg-white border-l border-slate-200">
      {/* Tab bar */}
      <div className="flex border-b border-slate-200 shrink-0">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-xs font-medium transition-colors ${
              activeTab === tab
                ? 'text-blue-600 border-b-2 border-blue-600 bg-white'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {activeTab === 'Tool Trace' && (
          <div className="p-3">
            {toolCalls.length === 0 ? (
              <p className="text-xs text-slate-400">No tool calls yet. Send a message to see traces.</p>
            ) : (
              toolCalls.map((tc, i) => <ToolCallTrace key={i} toolCall={tc} index={i} />)
            )}
          </div>
        )}

        {activeTab === 'Memory' && (
          <SessionMemory sessionState={sessionState} />
        )}

        {activeTab === 'Eval' && (
          <EvalDashboard />
        )}
      </div>
    </div>
  )
}
