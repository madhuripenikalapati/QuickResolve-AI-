export default function SessionMemory({ sessionState }) {
  if (!sessionState) return <p className="text-xs text-slate-400 p-3">No session yet.</p>

  const fields = [
    { label: 'Stage', value: sessionState.stage },
    { label: 'Turn', value: sessionState.turn_count },
    { label: 'Buyer', value: sessionState.buyer_name || '—' },
    { label: 'Active product', value: sessionState.active_product?.name || '—' },
    { label: 'Active order', value: sessionState.active_order_id || '—' },
    { label: 'Payment pref', value: sessionState.payment_preference || '—' },
    { label: 'Pending clarification', value: sessionState.pending_clarification || '—' },
  ]

  return (
    <div className="p-3 space-y-1">
      {fields.map(({ label, value }) => (
        <div key={label} className="flex items-start gap-2 text-xs">
          <span className="text-slate-400 shrink-0 w-36">{label}</span>
          <span className="font-mono text-slate-700 break-all">{String(value)}</span>
        </div>
      ))}

      {sessionState.cart?.length > 0 && (
        <div className="mt-2">
          <span className="text-xs text-slate-400">Cart</span>
          <pre className="text-[11px] font-mono text-slate-600 mt-1 overflow-x-auto">
            {JSON.stringify(sessionState.cart, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
