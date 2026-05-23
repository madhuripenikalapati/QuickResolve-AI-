export default function ProductCards({ products }) {
  if (!products || products.length === 0) return null

  return (
    <div className="mt-3">
      <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-thin">
      {products.map((p) => (
        <div
          key={p.product_id}
          className="shrink-0 w-40 bg-white border border-slate-100 rounded-xl shadow-sm overflow-hidden"
        >
          <div className="relative">
            <img
              src={p.image_url}
              alt={p.name}
              className="w-full h-44 object-cover"
              loading="lazy"
              onError={e => {
                e.target.onerror = null
                e.target.src = p.image_fallback || `https://placehold.co/300x400/f1f5f9/94a3b8?text=${encodeURIComponent(p.name)}`
              }}
            />
            {p.is_custom_stitched && (
              <span className="absolute top-1.5 left-1.5 bg-purple-600 text-white text-[9px] font-semibold px-1.5 py-0.5 rounded-full">
                Custom
              </span>
            )}
          </div>
          <div className="p-2">
            <p className="text-xs font-medium text-slate-800 leading-tight line-clamp-2">{p.name}</p>
            <p className="text-xs font-bold text-blue-600 mt-1">₹{p.price?.toLocaleString('en-IN')}</p>
            {p.fabric && (
              <p className="text-[10px] text-slate-400 mt-0.5 truncate">{p.fabric}</p>
            )}
            <div className="mt-1.5 flex flex-wrap gap-1">
              {Object.entries(p.sizes || {})
                .filter(([, qty]) => qty > 0)
                .slice(0, 4)
                .map(([size]) => (
                  <span key={size} className="text-[9px] bg-slate-100 text-slate-600 px-1 py-0.5 rounded font-mono">
                    {size}
                  </span>
                ))}
            </div>
          </div>
        </div>
      ))}
      </div>
      {products.length > 2 && (
        <p className="text-[10px] text-slate-400 mt-1 text-right pr-1">← scroll to see more</p>
      )}
    </div>
  )
}
