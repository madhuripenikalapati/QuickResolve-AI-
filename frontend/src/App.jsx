import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import DebugPanel from './components/DebugPanel'
import { PanelRightOpen, PanelRightClose } from 'lucide-react'

export default function App() {
  const [toolCalls, setToolCalls] = useState([])
  const [sessionState, setSessionState] = useState(null)
  const [debugOpen, setDebugOpen] = useState(true)

  function handleTurnComplete(newToolCalls, newSessionState) {
    setToolCalls(newToolCalls)
    setSessionState(newSessionState)
  }

  return (
    <div className="h-screen flex flex-col bg-slate-100">
      {/* Top bar */}
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">Q</div>
          <span className="font-semibold text-slate-800 text-sm">QuickResolve AI</span>
          <span className="text-slate-300 text-sm">·</span>
          <span className="text-xs text-slate-400">Taara Boutique</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400 hidden sm:block">Debug panel</span>
          <button
            onClick={() => setDebugOpen(o => !o)}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            {debugOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat panel */}
        <div className={`flex flex-col transition-all duration-200 ${debugOpen ? 'w-[60%]' : 'w-full'}`}>
          <ChatPanel onTurnComplete={handleTurnComplete} />
        </div>

        {/* Debug panel */}
        {debugOpen && (
          <div className="w-[40%] flex flex-col overflow-hidden border-l border-slate-200">
            <DebugPanel toolCalls={toolCalls} sessionState={sessionState} />
          </div>
        )}
      </div>
    </div>
  )
}
