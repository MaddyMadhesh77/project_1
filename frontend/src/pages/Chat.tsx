import { useState } from 'react'
import { useChat } from '../lib/queries'
import type { ChatMessageIn } from '../lib/api'

interface DisplayMessage extends ChatMessageIn {
  id: string
}

export default function Chat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const chat = useChat()

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || chat.isPending) return

    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: text }])
    setInput('')

    chat.mutate(
      { conversation_id: conversationId, message: text, history },
      {
        onSuccess: (data) => {
          setConversationId(data.conversation_id)
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: 'assistant', content: data.reply },
          ])
        },
      },
    )
  }

  return (
    <div className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <h1 className="mb-4 text-xl font-semibold text-neutral-800 dark:text-neutral-100">
        RecoverMem
      </h1>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        {messages.length === 0 && (
          <p className="text-sm text-neutral-400">
            Say something like &ldquo;I live in Bangalore and I like Python&rdquo;.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <span
              className={`inline-block max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                m.role === 'user'
                  ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                  : 'bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-100'
              }`}
            >
              {m.content}
            </span>
          </div>
        ))}
        {chat.isPending && <p className="text-sm text-neutral-400">Thinking…</p>}
        {chat.isError && (
          <p className="text-sm text-red-500">Something went wrong: {chat.error.message}</p>
        )}
      </div>

      <form onSubmit={sendMessage} className="mt-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message..."
          className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
        <button
          type="submit"
          disabled={chat.isPending}
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          Send
        </button>
      </form>
    </div>
  )
}
