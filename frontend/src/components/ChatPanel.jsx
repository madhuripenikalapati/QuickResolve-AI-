import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import MessageBubble from './MessageBubble'
import { sendMessageStream } from '../api'

export default function ChatPanel({ onTurnComplete }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hi! Welcome to Taara Boutique 👋 How can I help you today? Looking for something to wear, or do you have an order question?', intent: 'general', confidence: 1.0 }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const [stage, setStage] = useState('discovery')
  const [turnCount, setTurnCount] = useState(0)
  const [activeProduct, setActiveProduct] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    const assistantIndex = messages.length + 1
    let firstToken = true

    try {
      await sendMessageStream(
        text,
        sessionId,
        (token) => {
          if (firstToken) {
            firstToken = false
            setLoading(false)
            setMessages(prev => [...prev, { role: 'assistant', content: token, intent: null, confidence: null, products: null }])
          } else {
            setMessages(prev => {
              const updated = [...prev]
              updated[assistantIndex] = { ...updated[assistantIndex], content: updated[assistantIndex].content + token }
              return updated
            })
          }
        },
        (meta) => {
          const activeProduct = meta.session_state?.active_product
          const toolCalls = meta.tool_calls || []
          const usedSessionData = toolCalls.some(tc => tc.tool === 'use_session_data')
          let products = toolCalls
            .filter(tc => tc.tool === 'search_catalog' || tc.tool === 'use_session_data')
            .map(tc => tc.result)
            .find(r => Array.isArray(r) && r.length > 0) || null

          // check_availability returns a single product in result.product — render it as a card
          if (!products) {
            const availResult = toolCalls.find(tc => tc.tool === 'check_availability' && tc.result?.product)
            if (availResult) products = [availResult.result.product]
          }

          // Only collapse to active product when using session data (product selection),
          // not on fresh catalog searches (browsing by color, category, etc.)
          if (usedSessionData && activeProduct && products && products.length > 1) {
            const match = products.find(p => p.product_id === activeProduct.product_id)
            if (match) products = [match]
          }

          setMessages(prev => {
            const updated = [...prev]
            updated[assistantIndex] = {
              ...updated[assistantIndex],
              intent: meta.intent,
              confidence: meta.confidence,
              products,
            }
            return updated
          })
          setStage(meta.session_state?.stage || 'discovery')
          setTurnCount(meta.session_state?.turn_count || 0)
          setActiveProduct(meta.session_state?.active_product?.name || null)
          onTurnComplete(meta.tool_calls, meta.session_state)
        }
      )
    } catch (e) {
      const errMsg = { role: 'assistant', content: `Sorry, something went wrong: ${e.message}`, intent: 'error', confidence: 0 }
      if (firstToken) {
        setMessages(prev => [...prev, errMsg])
      } else {
        setMessages(prev => { const u = [...prev]; u[assistantIndex] = errMsg; return u })
      }
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Session info bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-white border-b border-slate-200 text-xs text-slate-500 shrink-0">
        <span className="font-medium text-slate-700">Taara Boutique</span>
        <span className="text-slate-300">|</span>
        <span>Stage: <span className="font-mono text-blue-600">{stage}</span></span>
        <span>Turns: <span className="font-mono">{turnCount}</span></span>
        {activeProduct && (
          <>
            <span className="text-slate-300">|</span>
            <span className="truncate max-w-[160px]">📦 {activeProduct}</span>
          </>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 bg-slate-50">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {loading && (
          <div className="flex justify-start mb-3">
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-semibold mr-2 mt-1 shrink-0">
              NB
            </div>
            <div className="bg-white border border-slate-100 shadow-sm rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 bg-white border-t border-slate-200 shrink-0">
        <div className="flex items-end gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-100 transition-all">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Taara Boutique..."
            rows={1}
            className="flex-1 bg-transparent text-sm resize-none outline-none text-slate-800 placeholder-slate-400 max-h-32"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="p-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <Send size={14} />
          </button>
        </div>
        <p className="text-[10px] text-slate-400 mt-1 text-center">Press Enter to send · Shift+Enter for newline</p>
      </div>
    </div>
  )
}
