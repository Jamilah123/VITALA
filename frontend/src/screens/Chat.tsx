import { useEffect, useRef, useState, type FormEvent } from "react";
import { Chip } from "../components/forms";
import { Icon } from "../components/Icon";
import { Screen } from "../components/layout";
import { CANNED_TOPICS, CHAT_INTRO, FREE_TEXT_REPLY } from "../demo/chat";

interface Message {
  id: number;
  from: "user" | "preview";
  text: string;
}

const MAX_LENGTH = 500;

/**
 * A preview of the assistant's layout, not an assistant. Replies are fixed text
 * that appears at once: no typing indicator or delay suggests anything is thinking.
 */
export function Chat() {
  const [messages, setMessages] = useState<Message[]>([{ id: 0, from: "preview", text: CHAT_INTRO }]);
  const [text, setText] = useState("");
  const nextId = useRef(1);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages]);

  const exchange = (question: string, reply: string) => {
    const questionId = nextId.current++;
    const replyId = nextId.current++;
    setMessages((previous) => [
      ...previous,
      { id: questionId, from: "user", text: question },
      { id: replyId, from: "preview", text: reply },
    ]);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = text.trim();
    if (!question) return;
    exchange(question, FREE_TEXT_REPLY);
    setText("");
  };

  return (
    <Screen
      title="اسأل Vitala"
      demo
      demoText="هذه محاكاة وليست ذكاءً اصطناعياً: الردود مكتوبة مسبقاً، ولا يوجد اتصال بأي نموذج."
    >
      <p className="note">عند توفره، سيشرح المساعد معلوماتك والفحوصات التي قد تنطبق ومصادرها، ولن يشخّص الأمراض أو يغيّر العلاج.</p>
      <div className="chat" aria-live="polite">
        {messages.map((message) => (
          <div key={message.id} className={`bubble bubble--${message.from}`}>
            {message.from === "preview" && <strong className="bubble__tag">رد مكتوب مسبقاً</strong>}
            <p>{message.text}</p>
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="chips chips--scroll" role="group" aria-label="أسئلة جاهزة">
        {CANNED_TOPICS.map((topic) => (
          <Chip key={topic.id} selected={false} onClick={() => exchange(topic.label, topic.reply)}>
            {topic.label}
          </Chip>
        ))}
      </div>
      <form className="chat-input" onSubmit={submit}>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          maxLength={MAX_LENGTH}
          placeholder="الأسئلة المكتوبة غير مدعومة بعد"
          aria-label="كتابة سؤال. الأسئلة المكتوبة غير مدعومة بعد"
        />
        <button type="submit" className="send-btn" aria-label="إرسال" disabled={!text.trim()}>
          <Icon name="send" size={20} />
        </button>
      </form>
    </Screen>
  );
}
