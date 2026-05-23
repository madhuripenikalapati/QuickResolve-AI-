import { useState } from 'react'
import { ChevronDown, ChevronRight, CheckCircle, XCircle } from 'lucide-react'

export default function ToolCallTrace({ toolCall, index }) {
  const [argsOpen, setArgsOpen] = useState(false)
  const [resultOpen, setResultOpen] = useState(false)
  const hasError = !!toolCall.error

  return (
    <div className={`border rounded-lg overflow-hidden mb-2 text-xs ${hasError ? 'border-red-200' : 'border-slate-200'}`}>
      <div className={`flex items-center gap-2 px-3 py-2 ${hasError ? 'bg-red-50' : 'bg-slate-50'}`}>
        {hasError
          ? <XCircle size={13} className="text-red-500 shrink-0" />
          : <CheckCircle size={13} className="text-green-500 shrink-0" />
        }
        <span className="font-mono font-medium text-slate-700">{toolCall.tool}</span>
        <span className="ml-auto text-slate-400">#{index + 1}</span>
      </div>

      {/* Args */}
      <div className="border-t border-slate-100">
        <button
          onClick={() => setArgsOpen(o => !o)}
          className="w-full flex items-center gap-1.5 px-3 py-1.5 text-slate-500 hover:bg-slate-50 transition-colors"
        >
          {argsOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          <span>args</span>
        </button>
        {argsOpen && (
          <pre className="px-3 pb-2 text-[11px] font-mono text-slate-600 bg-white overflow-x-auto">
            {JSON.stringify(toolCall.args, null, 2)}
          </pre>
        )}
      </div>

      {/* Result / Error */}
      <div className="border-t border-slate-100">
        <button
          onClick={() => setResultOpen(o => !o)}
          className="w-full flex items-center gap-1.5 px-3 py-1.5 text-slate-500 hover:bg-slate-50 transition-colors"
        >
          {resultOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          <span>{hasError ? 'error' : 'result'}</span>
        </button>
        {resultOpen && (
          <pre className={`px-3 pb-2 text-[11px] font-mono overflow-x-auto ${hasError ? 'text-red-600 bg-red-50' : 'text-slate-600 bg-white'}`}>
            {hasError ? toolCall.error : JSON.stringify(toolCall.result, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
