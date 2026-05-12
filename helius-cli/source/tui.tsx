// tui.tsx — Helius Code · polished terminal UI
import React, { useEffect, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import TextInput from "ink-text-input";

import { createAgent } from "./agent.js";
import { runAgent } from "./agents/runner.js";
import { configureLogging } from "./utils/logging_setup.js";
import { getSettings } from "./utils/config.js";
import { getLogger } from "./utils/logger.js";

// ─── Identity (rename here to switch to "blu" or "sushi") ─────────────────
//
//   HELIUS mascot: ancient sun-god ☉, warm amber/flame palette
//   BLU    mascot: swap MASCOT_LINES + C.primary to "#38bdf8" (sky-blue)
//   SUSHI  mascot: swap MASCOT_LINES to the fish variant below + "#f97316"
//
const AGENT_NAME = "HELIUS";
const AGENT_SUB  = "industrial autonomous engineer";

//  ── Industrial mascot ──────────────────────────────────────────────────
const MASCOT_LINES = [
  { text: "      _______      ", dim: true },
  { text: "     /       \\     " },
  { text: "    |  [☉]   |     " },
  { text: "     \\_______/     " },
  { text: "    /|_______|\\    ", dim: true },
];
//  ── Fish mascot (SUSHI) — swap MASCOT_LINES above ─────────────────────
//  { text: "    ><(((º>        " },
//  { text: "  ~~ ~~~~ ~~~      " },
//  { text: " ><(( º> ><(º>    " },   // hero line
//  { text: "  ~~ ~~~~ ~~~      " },
//  { text: "    ><(((º>        " },

//  ── Wave mascot (BLU) — swap MASCOT_LINES above ────────────────────────
//  { text: "   ∿ ∿ ∿ ∿ ∿ ∿    ",  dim: true },
//  { text: "  ∿∿ ( ◉ ) ∿∿     "              },
//  { text: "   ∿  ~~~  ∿      "               },
//  { text: "  ∿ ∿ ∿ ∿ ∿ ∿     ",  dim: true },

// ─── Palette ──────────────────────────────────────────────────────────────
const C = {
  primary:  "#f59e0b",   // amber — main brand colour
  accent:   "#d97757",   // warm orange — agent replies
  flame:    "#ea580c",   // deep flame — active/running state
  teal:     "#2dd4bf",   // tool calls
  green:    "#4ade80",   // ready / success
  red:      "#f87171",   // errors
  white:    "#f1f5f9",   // user messages
  dim:      "#6b7280",   // secondary text
  muted:    "#374151",   // very quiet chrome
} as const;

const logger = getLogger("tui");

// ─── Types ────────────────────────────────────────────────────────────────
type MsgKind = "system" | "user" | "agent" | "tool" | "error";

type Message = {
  kind:  MsgKind;
  text:  string;
  ts:    Date;
};

// ─── Spinner (no extra deps) ───────────────────────────────────────────────
const SPIN = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"];

function useSpinner(active: boolean) {
  const [f, setF] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setF(n => (n + 1) % SPIN.length), 80);
    return () => clearInterval(id);
  }, [active]);
  return SPIN[f];
}

// ─── Helpers ──────────────────────────────────────────────────────────────
function hms(d: Date) {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function rule(label?: string) {
  const line = "─".repeat(label ? 3 : 52);
  if (!label) return <Text color={C.muted}>{line}</Text>;
  return (
    <Text color={C.muted}>
      {line}{" "}
      <Text color={C.dim}>{label}</Text>
      {"  "}{"─".repeat(Math.max(0, 40 - label.length))}
    </Text>
  );
}

// ─── Message row ──────────────────────────────────────────────────────────
const KIND_ICON: Record<MsgKind, string> = {
  user:   "▸",
  agent:  "◂",
  tool:   "⚙",
  error:  "✗",
  system: "·",
};

const KIND_COLOR: Record<MsgKind, string> = {
  user:   C.white,
  agent:  C.accent,
  tool:   C.teal,
  error:  C.red,
  system: C.dim,
};

function MessageRow({ msg }: { msg: Message }) {
  const color = KIND_COLOR[msg.kind];
  return (
    <Box gap={1} marginBottom={0}>
      <Text color={C.muted}>{hms(msg.ts)}</Text>
      <Text color={color}>{KIND_ICON[msg.kind]}</Text>
      <Text color={color} wrap="wrap">{msg.text}</Text>
    </Box>
  );
}

// ─── Mascot splash ────────────────────────────────────────────────────────
function MascotPanel({ loading }: { loading: boolean }) {
  return (
    <Box flexDirection="row" gap={3} marginBottom={1}>
      {/* ASCII art */}
      <Box flexDirection="column">
        {MASCOT_LINES.map((line, i) => (
          React.createElement(                                                                                                      
               Text,                                                                                                                   
                { key: i, color: line.dim ? C.muted : i === 2 ? C.primary : C.accent },                                                 
                line.text                                                                                                               
            )  
        ))}
      </Box>

      {/* Name + help */}
      <Box flexDirection="column" justifyContent="center">
        <Text bold color={C.primary}>{AGENT_NAME}</Text>
        <Text color={C.dim}>{AGENT_SUB}</Text>

        <Box flexDirection="column" marginTop={1}>
          <Text color={C.dim}>
            {"  "}
            <Text color={C.muted}>enter</Text>
            {"  submit a task"}
          </Text>
          <Text color={C.dim}>
            {"  "}
            <Text color={C.muted}>task architect</Text>
            {" delegate planning"}
          </Text>
          <Text color={C.dim}>
            {"  "}
            <Text color={C.muted}>task reviewer</Text>
            {" delegate auditing"}
          </Text>
          <Text color={C.dim}>
            {"  "}
            <Text color={C.muted}>/clear</Text>
            {"  reset transcript"}
          </Text>
        </Box>

        {loading && (
          <Box marginTop={1}>
            <Text color={C.muted}>⟳ loading agent…</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────
export default function App({ resume }: { resume: string | null }) {
  const { exit } = useApp();

  const [agent,      setAgent]      = useState<any>(null);
  const [threadId,   setThreadId]   = useState<string | null>(resume);
  const [inputValue, setInputValue] = useState("");
  const [busy,       setBusy]       = useState(false);
  const [messages,   setMessages]   = useState<Message[]>([]);

  const spin = useSpinner(busy);

  const push = (kind: MsgKind, text: string) =>
    setMessages(prev => [...prev, { kind, text, ts: new Date() }]);

  // Boot agent
  useEffect(() => {
    (async () => {
      const s = getSettings();
      configureLogging(s.observability.log_level, s.observability.log_format);
      logger.info("tui init");
      const built = await createAgent();
      setAgent(built);
      logger.info("tui agent ready");
    })();
  }, []);

  // Global keys
  useInput((_ch, key) => {
    if (key.ctrl && _ch === "c") exit();
  });

  const submit = async (raw: string) => {
    const task = raw.trim();
    if (!task || !agent || busy) return;

    if (task === "/clear") {
      logger.info("tui clear");
      setMessages([]);
      setInputValue("");
      return;
    }

    setInputValue("");
    setBusy(true);
    logger.info(`tui submit task_len=${task.length}`);
    push("user", task);

    try {
      const { result, threadId: usedTid } = await runAgent(task, { agent, threadId });
      setThreadId(usedTid);
      push(result ? "agent" : "error", result ? "Task completed." : "Task failed.");
      logger.info(`tui runAgent result=${Boolean(result)} thread=${usedTid}`);
    } catch (err: any) {
      push("error", err?.message ?? "Unknown error.");
      logger.error("tui runAgent error", err);
    } finally {
      setBusy(false);
    }
  };

  const sessionTag = threadId ? `#${threadId.slice(0, 8)}` : "new session";
  const statusText = busy
    ? <Text color={C.flame}>{spin} running</Text>
    : agent
    ? <Text color={C.green}>● ready</Text>
    : <Text color={C.dim}>○ loading</Text>;

  return (
    <Box flexDirection="column" paddingX={1} paddingY={1}>

      {/* ── Header bar ──────────────────────────────────────────── */}
      <Box justifyContent="space-between" marginBottom={1}>
        <Box gap={2}>
          <Text bold color={C.primary}>⬡ {AGENT_NAME.toLowerCase()}</Text>
          <Text color={C.muted}>code</Text>
        </Box>
        <Box gap={3}>
          {statusText}
          <Text color={C.muted}>{sessionTag}</Text>
        </Box>
      </Box>

      {rule()}

      {/* ── Mascot ──────────────────────────────────────────────── */}
      <Box marginY={1}>
        <MascotPanel loading={!agent} />
      </Box>

      {rule("conversation")}

      {/* ── Message list ────────────────────────────────────────── */}
      <Box flexDirection="column" marginTop={1} minHeight={8}>
        {messages.length === 0 ? (
          <Text color={C.muted}>  No messages yet.</Text>
        ) : (
                    messages.map((msg, i) =>                                                                                                  
                React.createElement(MessageRow, { key: i, msg })                                                                        
            )      
        )}

        {busy && (
          <Box marginTop={1} gap={1}>
            <Text color={C.accent}>{spin}</Text>
            <Text color={C.dim}>
              thinking{"  "}·{"  "}running tools{"  "}·{"  "}updating state
            </Text>
          </Box>
        )}
      </Box>

      {rule()}

      {/* ── Input ───────────────────────────────────────────────── */}
      <Box
        borderStyle="round"
        borderColor={busy ? C.muted : C.primary}
        paddingX={1}
        marginTop={1}
      >
        <Text color={busy ? C.muted : C.primary}>▸{"  "}</Text>
        <Box flexGrow={1}>
          <TextInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={submit}
            placeholder={busy ? "waiting for agent…" : "describe a task…"}
          />
        </Box>
      </Box>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <Box marginTop={1} justifyContent="space-between">
        <Text color={C.muted}>
          <Text color={C.dim}>enter</Text>
          {" submit  "}
          <Text color={C.dim}>ctrl+c</Text>
          {" quit  "}
          <Text color={C.dim}>/clear</Text>
          {" reset"}
        </Text>
        <Text color={C.muted}>
          {AGENT_NAME.toLowerCase()} · {AGENT_SUB}
        </Text>
      </Box>

    </Box>
  );
}
