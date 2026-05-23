import ProductCards from './ProductCards'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const hasProducts = !isUser && message.products && message.products.length > 0

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-semibold mr-2 mt-1 shrink-0">
          NB
        </div>
      )}
      <div className={`${hasProducts ? 'max-w-[95%] w-full' : 'max-w-[75%]'}`}>
        <div
          className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-white text-slate-800 shadow-sm border border-slate-100 rounded-bl-sm'
          }`}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
          {message.intent && !isUser && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="text-xs text-slate-400">{message.intent}</span>
              {message.confidence !== undefined && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-mono ${
                  message.confidence >= 0.8 ? 'bg-green-100 text-green-700' :
                  message.confidence >= 0.5 ? 'bg-yellow-100 text-yellow-700' :
                  'bg-red-100 text-red-700'
                }`}>
                  {(message.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>
          )}
        </div>

        {hasProducts && <ProductCards products={message.products} />}
      </div>
    </div>
  )
}
