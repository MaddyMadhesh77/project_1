import { useState } from 'react'
import { useChat } from '../lib/queries'
import type { ChatMessageIn } from '../lib/api'

interface DisplayMessage extends ChatMessageIn {
  id: string
  // Shown under an assistant reply when some extracted memories failed to store.
  warning?: string
}

// Must not exceed ChatRequest.history's max_length on the backend
// (routes/chat.py): sending the whole ever-growing transcript made every send
// after the 51st message fail with a 422. Only the most recent turns are
// useful context for the reply anyway.
const MAX_HISTORY = 50

// Chat history previously lived only in React component state:
// a page refresh silently lost the whole conversation, including
// conversation_id, so /chat's server-side memory of "this conversation"
// and the client's transcript of it diverged. localStorage keeps both
// together across reloads, without standing up a backend chat-history table.
const STORAGE_KEY = 'recovermem_chat'

interface StoredChat {
  conversationId: string | undefined
  messages: DisplayMessage[]
}

function loadStoredChat(): StoredChat {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { conversationId: undefined, messages: [] }
    const parsed = JSON.parse(raw) as StoredChat
    return { conversationId: parsed.conversationId, messages: parsed.messages ?? [] }
  } catch {
    return { conversationId: undefined, messages: [] }
  }
}

export default function Chat() {
  const [initial] = useState(loadStoredChat)
  const [messages, setMessages] = useState<DisplayMessage[]>(initial.messages)
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState<string | undefined>(initial.conversationId)
  const chat = useChat()

  const persist = (nextMessages: DisplayMessage[], nextConversationId: string | undefined) => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ conversationId: nextConversationId, messages: nextMessages }),
    )
  }

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || chat.isPending) return

    const history = messages.slice(-MAX_HISTORY).map(({ role, content }) => ({ role, content }))
    const withUserMessage = [...messages, { id: crypto.randomUUID(), role: 'user' as const, content: text }]
    setMessages(withUserMessage)
    persist(withUserMessage, conversationId)
    setInput('')

    chat.mutate(
      { conversation_id: conversationId, message: text, history },
      {
        onSuccess: (data) => {
          setConversationId(data.conversation_id)
          const withReply = [
            ...withUserMessage,
            {
              id: crypto.randomUUID(),
              role: 'assistant' as const,
              content: data.reply,
              warning:
                data.failed_candidates > 0
                  ? `${data.failed_candidates} memory candidate${data.failed_candidates === 1 ? '' : 's'} failed to store`
                  : undefined,
            },
          ]
          setMessages(withReply)
          persist(withReply, data.conversation_id)
        },
      },
    )
  }

  const clearChat = () => {
    localStorage.removeItem(STORAGE_KEY)
    setMessages([])
    setConversationId(undefined)
  }

  return (
    <div className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-800 dark:text-neutral-100">RecoverMem</h1>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="text-xs text-neutral-500 hover:underline dark:text-neutral-400"
          >
            Clear chat
          </button>
        )}
      </div>

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
            {m.warning && <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">⚠ {m.warning}</p>}
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
